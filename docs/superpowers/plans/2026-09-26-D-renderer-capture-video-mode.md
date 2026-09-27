# Renderer, Captures and Video Mode (stream D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the studio's picture side: the Remotion renderer in `video/` (Episode + Thumbnail compositions driven by `timeline.json`, the NERV block library for the four topic types, frame-driven motion, the layout lint, and the `lint.ts` / `render.ts` / `still.ts` scripts), the capture package `pipeline/studio/capture/` (platform takes of the real site, globe and Mapbox takes, source-page captures, exact top-down frames) and the frontend's `?video=1` capture mode with the recorder's studio scenes, all bound to the NVIDIA RTX 3080 and proving it.

**Architecture:** `timeline.json` (plan C's compiler) is the only input of the renderer: `calculateMetadata` validates it against the block registry, measures narration and images in the browser and sets duration, fps and size, so nothing about an episode is hard-coded. Every frame is a pure function of `useCurrentFrame()`; claim statuses and the probability meter are episode-wide state derived from the cues. Text and markers register their boxes in lint mode, and a pure overlap checker reports violations as JSON console lines that `lint.ts` collects. The captures write media plus a manifest (plan C's contract C7); every Chrome they drive, and Remotion's own browser, proves from its WebGL renderer that it draws on the NVIDIA, every H.264/HEVC encode is NVENC on GPU 0 (spec 4.11). The frontend gains a `?video=1` mode (panels hidden, HUD scale, a ready flag) and a `screenPoint` demo call, the recorder gains landscape studio scenes that grab every frame exactly.

**Tech Stack:** Remotion 4.0.529 (`remotion`, `@remotion/bundler`, `@remotion/renderer`, `@remotion/cli`, `@remotion/media`, `@remotion/fonts`, all exactly 4.0.529), React 18.3.1, TypeScript 5.9.3, vitest 4.0.18, tsx 4.20.6, Node 22; Python 3.11 syntax (local venv 3.13), Playwright (Chrome channel, local only), httpx, Pillow, ffmpeg with `hevc_nvenc`/`h264_nvenc`; the frontend's Puppeteer recorder (`ancient-nerds-map/video/record.ts`), vitest and three.js.

Spec: `docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md` sections 4.5 (capture), 4.6 (video mode), 4.8 (renderer), 4.10 (topic types) and 4.11 (GPU). Plan C (`2026-09-26-C-studio-core-and-paper-studio.md`) is final and defines what this plan must deliver: contracts C5 (block registry), C6 (resolved props), C7 (capture functions), C8 (timeline.json) and C9 (scripts and the per-render public dir); its Tasks 16, 20, 21, 24 and 25 call this plan's code. Every code block below was applied script-driven to a scratch copy of this worktree and run; see "Planning verification" at the end.

---

## Ground rules for every task

- Work in `C:/PythonProjects/AncientMap-studio` (Git Bash). Commands run from the worktree root unless a step says `cd video` or `cd ancient-nerds-map`; in Claude Code the cwd resets between calls, so prefix each command with `cd /c/PythonProjects/AncientMap-studio && `.
- Python is always `./.venv/Scripts/python.exe` (the main checkout's venv). A single Python test file: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/<file> -m "not integration and not live_llm" -q -rs`. Python lint gate (run before every Python commit; CI runs the same three):
  `./.venv/Scripts/python.exe -m ruff check pipeline/studio/capture tests/pipeline/studio/capture && ./.venv/Scripts/python.exe -m ruff format --check pipeline/studio/capture tests/pipeline/studio/capture && ./.venv/Scripts/python.exe -m vulture pipeline/studio .vulture_whitelist.py --min-confidence 80`
  Expected: `All checks passed!`, `N files already formatted`, no vulture output.
- Renderer: a single test file `cd video && npx vitest run test/<file>`; the type gate `cd video && npx tsc --noEmit` (no output = clean). Frontend: `cd ancient-nerds-map && npx vitest run <file>`, `npm run type-check`, and the recorder's own types `npx tsc -p video/tsconfig.json --noEmit` (the frontend tsconfig covers `src/` only).
- Commit only the files the task lists, with explicit `git add <paths>` (or `git rm <paths>`); several streams share this worktree, so never `git add -A`, `git add .` or `git commit -a`. Message: one English sentence, then the attribution line:
  `git commit -m "<sentence>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`
- No fallback code (CLAUDE.md): no `try/except` or `catch` that returns empty, no "if possible" paths. Every capture failure is a `CaptureError` (a `StudioError`, CLI exit 2); every renderer failure throws and the node scripts exit 1 with the message on stderr.
- Remotion rules (spec 4.8): all animation from `useCurrentFrame()`, no CSS animations or transitions, no timers or clocks in a render, `<Video>`/`<Audio>` from `@remotion/media` without fallback, fonts through `@remotion/fonts` from files in the public dir, even dimensions, randomness only through `random(seed)` (the renderer needs none). `test/rules.test.ts` (Task 18) enforces them over `video/src`.
- GPU rule (spec 4.11, binding): every Chrome the studio drives runs on the NVIDIA and proves it from its WebGL renderer string before it records or renders; every H.264/HEVC encode is `h264_nvenc`/`hevc_nvenc` with `-gpu 0`; a missing NVENC or a render on the AMD, SwiftShader or the Basic Render Driver is an error, never a software run. Remotion's `hardwareAcceleration: 'if-possible'` is not used anywhere.
- Tests never touch `video-assets/`, production or the network, except the tests marked as needing the workstation (NVENC, headed Chrome), which skip with a reason elsewhere (`-rs` shows it). The smoke render and the real captures (Tasks 22 and 36) are local steps, not CI.
- Do not create or edit `pipeline/studio/__init__.py` or `pipeline/studio/errors.py` (plan C Task 1 owns them). The capture package imports `pipeline.studio.errors.StudioError` from there.

## Dependencies and order

| Tasks | Need | Check before starting |
|---|---|---|
| 1-22 (renderer) | nothing from other streams | none |
| 23-32 (captures) | plan C Task 1: `pipeline/studio/errors.py` with `StudioError` and its `config.py` with `CAPTURE_ID_RE` and `CAPTURE_KINDS` (the one definition of C7's capture ids and kinds, which Task 23 imports), `REPO` (Task 27) and `check_slug` (Task 29) | check C1 |
| 29 (source pages) and 32 (package exports, imports `sources.py`) | also plan A Task 2: `pipeline/lyra/theo_publishing.py` with `EVIDENCE_ID_RE`, the one definition of the evidence-id format (contract C9), which Task 29 imports (Task 32's `__init__.py` imports Task 29's `sources.py`, so every `import pipeline.studio.capture.<module>` needs it from then on) | check A2 |
| 33-34 (frontend) | nothing | none |
| 35 (studio scenes) | Tasks 33-34 | both committed |
| 36 (real captures, local) | Tasks 23-35, `VITE_MAPBOX_ACCESS_TOKEN` in the main checkout's `.env`, an awake, unlocked Windows display | none |
| 37 (whole-stream verification) | everything above; plan C Task 21: its golden `tests/pipeline/studio/golden_timeline.json`, which Task 37's contract test reads | check C21 |

Check C1 (prints five lines when plan C's Task 1 has landed):

```bash
grep -n "class StudioError" pipeline/studio/errors.py && grep -n "^REPO\|^CAPTURE_ID_RE\|^CAPTURE_KINDS\|^def check_slug" pipeline/studio/config.py
```

Check A2 (prints one line when plan A's Task 2 has landed):

```bash
grep -n "^EVIDENCE_ID_RE" pipeline/lyra/theo_publishing.py
```

Check C21 (prints the path when plan C's Task 21 has landed its golden timeline):

```bash
ls tests/pipeline/studio/golden_timeline.json
```

Recommended order: 1-22, then 33-35 (the frontend, independent of the captures), then 23-32 as soon as check C1 prints its line (Task 29 also waits for check A2; do Tasks 30 and 31 first if it prints nothing; Task 32 comes after Task 29), then 36 and 37. If a capture test fails with `ModuleNotFoundError: No module named 'pipeline.studio.errors'` or `ImportError: cannot import name 'CAPTURE_ID_RE' from 'pipeline.studio.config'`, plan C's (amended) Task 1 has not landed: switch to the renderer or frontend tasks. Never stub `errors.py`, `config.py` or `theo_publishing.py`: plans C and A own them. Likewise Task 37 starts only when check C21 prints the path; never write `golden_timeline.json` by hand, plan C's compiler writes it.

---

## Contracts this plan defines (plan C builds against these; they implement plan C's C5-C9)

### D1. Block registry `video/src/blocks/registry.json` (implements C5)

Written by `cd video && npm run registry` from `video/src/blocks/schemas.ts`; `test/registry.test.ts` fails when the committed file differs. Shape `{"blocks": {"<Block>": {"map": bool, "platform": bool, "drawn": [str], "props": <schema of type "object">}}}` (exactly these four keys), keywords only from C5's subset. `drawn` (owner decision 32) lists the prop paths whose strings the block's component draws: keys separated by `.`, a key suffixed with `[]` means every element of that array (`claims[].label`); `test/registry.test.ts` proves each pattern points at a string prop. It is the single definition of the drawn prop strings: plan C reads it from `registry.json` and keeps no copy. The 18 scene blocks (props arrive resolved per C6; a capture is the manifest with `path` renamed `src`):

| Block | map | platform | Props (required in bold) | Local cue targets (`show`/`hide`/`highlight`/`stamp`) |
|---|---|---|---|---|
| PhotoPlate | no | no | **image** (media), kenBurns `in\|out\|none`, label `{title, subtitle?}`, caption | show/hide/highlight: marker ids |
| MapboxTopdown | yes | no | **map** (capture kind `mapbox_topdown`, a still), lines `[{from, to}]` (place ids), label | show/highlight: place ids (the capture's `pin` events) |
| PlatformClip | yes | yes | **clip** (capture kind `platform`), start_s, camera `[{t, cx, cy, zoom}]` or follow (zoom); a zoom above `clip.width / 1920` (1.5 for the workstation's 2880x1620) upscales and is refused, label | none |
| GlobeShot | no | no | **clip** (capture kind `globe`, no map credits), start_s, label; each `place` event's `track` must run to the end of the take | show: place ids (the capture's `place` events with a label; unlabelled places are dots) |
| MapboxFlyover | yes | no | **clip** (capture kind `globe` with a Mapbox credit), start_s, label | none |
| SourceViewer | no | no | **page** (capture kind `source`), **evidence** | highlight: the evidence id |
| EvidenceCard | no | no | **evidence**, image (media) | highlight/stamp: the evidence id |
| QuoteCard | no | no | **evidence** (with a verbatim quote), attribution | highlight: the evidence id |
| ClaimBoard | no | no | **claims** (1-6), title | highlight: claim ids |
| Meter | no | no | **hypotheses** [a, b], **start** [a, b] summing to 100, title, note | none (global `meter` cues move it) |
| ScaleDrawing | no | no | **title**, **unit** `cm\|m\|km`, **basis**, **objects** (2-5 `{id, label, shape, width, height, x}`) | show: object ids |
| UnitGrid | no | no | **title**, **basis**, **unitLabel**, columns, **groups** (1-4 `{id, count, label, tone}`, at most 400 cells) | show: group ids |
| BarChart | no | no | **title**, **unit**, **basis**, **bars** (2-8 `{id, label, value, tone?}`; value a number or `[low, high]` when sources differ, drawn as a range), on a linear axis only (owner decision 31: no `scale` prop, so a script's `scale` is refused as `props.scale: not allowed`) | show: bar ids |
| Timeline | no | no | **title**, **from**, **to** (years, negative = BCE, no year 0), basis, **events** (1-10 `{id, year, label, tone}`) | show: event ids |
| Diagram | no | no | **title**, **width**, **height**, basis, **elements** (1-16 `{id, type, tone, ...geometry}`) | show: element ids |
| ListCard | no | no | **title**, **items** (1-5 `{id, text}`), note | show: item ids |
| ShareCard | no | no | **headline**, **url**, **lines** (0-3); the end card, the one place the link appears in the picture: only the last scene may use it (owner rule, full episodes and slices alike) | none |
| ScaleZoom | no | no | **title**, **unit**, **basis**, **small** and **large** (`{id, label, value}`, 0 < small < large): a linear zoom-out (owner decision 31), the small quantity drawn readable, then the camera pulls back linearly until the large one fits, the small one shrinking to a dot; the scene lasts at least 240 frames | show: `small.id`, `large.id` |

Spec 4.10's topic types map onto these blocks as Task 16 describes; type B's world distribution is a GlobeShot of a globe `distribution` take (D2: labelled case-file places plus unlabelled dots that plan C resolves from site ids, owner decision 15) or a PlatformClip whose take uses the `filter` and `toggle_layer` actions; type C's orders of magnitude are a UnitGrid up to 1:400 and a ScaleZoom beyond, linear only, never a log axis (owner decision 31).

Global cue verbs (any scene): `introduce <claim>` (a ClaimBoard of the episode must list the claim), `status <claim>` with `value` in `pending|supported|weakened|refuted|open`, `meter` (target `"meter"`, `value` [a, b] = 100; the episode needs a Meter scene). A claim introduced or re-statused in one scene shows so on every later ClaimBoard and EvidenceCard; the Meter picks up the last split; a claim's resolved `status` is what the board shows before the first `status` cue for it. Without a cue, elements appear on a staggered default schedule, so no block needs cues. The local cue column above is the single definition of the local cue rules: it is the `BLOCKS` table of `video/src/blocks/index.ts` (Task 17), and plan C's `script.py` mirrors it (its `LOCAL_CUES`, asserted to cover exactly the blocks of this registry) so a script is refused at `episode check`, before voice and capture, for the same cue reasons `lint.ts` would refuse its timeline. Every string the video draws must be drawable by the brand fonts (latin and latin-ext; `checkBlocks` refuses anything else, e.g. Greek or an arrow). A character must also be drawable in upper case: every code point of its full Unicode upper-case mapping must lie in the two ranges, because `heading()` and `hud()` draw upper case. So `µ` (drawn as Greek `Μ`) is refused. Only drawn strings are checked (owner decision 32): (1) a block's `drawn` prop paths; (2) of every capture prop (`clip`, `map`, `page`), exactly the capture's `credits` and the `label` of its `place` and `pin` events (never an event's `name` or `target`, a `url`, whose only drawn part is the ASCII hostname, the `title` of a `page` event, which records the page's own `<title>` and is drawn nowhere, or the `gpu` event's renderer); (3) the hook captions, chapter titles, timeline credits and thumbnail teasers. An original quote inside a captured source page (SourceViewer's `evidence.source.quote`), the page's own non-latin `<title>` and a non-latin URL path therefore pass, so a Greek, Hebrew or Chinese source page is shown as captured; a QuoteCard's quote is drawn and checked. Plan C's `episode check` applies the same definition (read from `registry.json`) to the script before voice and capture, and plan C's capture step checks (2) on every returned manifest, naming the capture (a source capture's only credit is `Source page: <ASCII hostname>`, so the check never refuses it for its page). Overlays that are not scene blocks: HookCaptions (the timeline's `captions`, hook only), Ticker (evidence counter), ChapterTag (3 s after each chapter start, none at 0:00), CreditLine (the scene's `credits`), LowerThird, Stamp, Panel.

### D2. Captures (implements C7) — `pipeline/studio/capture/__init__.py`

```python
record_platform(episode_dir: Path, spec: dict) -> dict   # kind "platform"
record_globe(episode_dir: Path, spec: dict) -> dict      # kind "globe"
capture_source(episode_dir: Path, spec: dict) -> dict    # kind "source"
mapbox_topdown(episode_dir: Path, spec: dict) -> dict    # kind "mapbox_topdown"
```

Each writes `captures/<id>.<ext>` and returns exactly `{"id", "kind", "path", "fps", "duration_s", "width", "height", "events", "credits"}` (a still has `fps` and `duration_s` null; `width`/`height` are the size of the written file). Clips are HEVC (`hevc_nvenc`, GPU 0, BT.709 limited range, `hvc1`, constant 60 fps, a keyframe per second, no B-frames). The first event of every browser capture is `{"t": 0, "name": "gpu", "label": "<WebGL renderer>"}`: the proof that it drew on the NVIDIA (spec 4.11 wants the renderer recorded; C7 has no other free field). Every failure is a `CaptureError` (a `StudioError`: plan C's CLI exits 2 with the message), raised before any side effect for a bad spec (unknown keys, a missing or non-numeric value, a value out of range) or a venv without Playwright, and carrying the cause for a failed ffmpeg/ffprobe run (tool, exit code, stderr tail), a refused Mapbox request (never the token) or a Playwright failure; a page that never gets ready names the likely cause, and a screencast without frames fails with its own message. Plan C's capture step (`captures.py`) refuses a returned manifest whose drawn strings fall outside D1's glyph rule, naming the capture: exactly its `credits` and the `label` of `place` and `pin` events. A source page's own `<title>` stays in its `page` event as a record and is never drawn (owner decision 32): SourceViewer's address bar and the credit `Source page: <host>` show only the ASCII (IDNA) hostname, so a non-latin page title or URL path never refuses a capture. The Playwright captures block the site's Umami tracker (`/pulse.js`), so no take counts as a visit. Spec shapes:

```json
{"id": "platform-01", "kind": "platform", "target": "local|production", "hud": 1.3,
 "actions": [{"do": "pause_rotation"}, {"do": "search", "q": "baalbek"},
             {"do": "click_result", "title": "Baalbek Stones"}, {"do": "fly_wait", "s": 3.0},
             {"do": "zoom", "to": 90},
             {"do": "open_details", "title": "Baalbek Stones"},
             {"do": "measure", "a": {"lat": 34.0, "lng": 36.2}, "b": {"lat": 34.01, "lng": 36.21}},
             {"do": "toggle_layer", "label": "Empire Borders"},
             {"do": "proximity", "at": {"lat": 34.0067, "lng": 36.2033}},
             {"do": "filter", "mode": "country|category|source", "label": "<legend entry>"},
             {"do": "wait", "s": 1.0}]}
{"id": "g1", "kind": "globe", "scene": "flyto", "lat": 34.0067, "lng": 36.2033, "distance": 1.35,
 "empire": "roman", "rotate_s": 1.5, "zoom_s": 2.0, "duration_s": 5, "place": {"id": "p1", "label": "Baalbek"}}
{"id": "g2", "kind": "globe", "scene": "places", "lead_s": 0.8, "interval_s": 0.6, "duration_s": 6,
 "places": [{"id": "p1", "label": "Baalbek", "lat": 34.0067, "lng": 36.2033}]}
{"id": "g3", "kind": "globe", "scene": "places", "lead_s": 0.5, "interval_s": 1.0, "duration_s": 8,
 "sweep_lng_deg": 150, "cam_lat": 35, "cam_lng_from": -30, "distance": 2.2, "places": [...]}
{"id": "g4", "kind": "globe", "scene": "distribution", "duration_s": 16,
 "places": [{"id": "w1", "lat": 29.9792, "lng": 31.1342, "label": "Giza"},
            {"id": "be81c1a6-5d0c-4f7e-9a51-3c2d7e8f9a10", "lat": 37.2231, "lng": 38.9224}]}
{"id": "m1", "kind": "globe", "scene": "mapbox_flyin", "name": "Baalbek", "lat": 34.0067, "lng": 36.2033,
 "country": "Lebanon", "orbit_zoom": 15.5, "duration_s": 8}
{"id": "m2", "kind": "globe", "scene": "mapbox_orbit", "name": "Baalbek", "lat": 34.0067, "lng": 36.2033,
 "zoom": 16.5, "pitch": 60, "bearing_from": 20, "bearing_to": 110, "duration_s": 6}
{"id": "src-dai", "kind": "source", "url": "https://...", "quote": "verbatim sentence of at least 12 chars"}
{"id": "paper-ev07", "kind": "source", "paper": "<paper slug>", "anchor": "ev-07"}
{"id": "td1", "kind": "mapbox_topdown", "center": {"lat": 34.0029, "lng": 36.2018}, "zoom": 15.0, "bearing": 0,
 "style": "satellite-v9|satellite-streets-v12", "width": 1280, "height": 720,
 "pins": [{"id": "p2", "label": "Quarry", "lat": 33.99917, "lng": 36.20028}]}
```

Platform actions: `zoom` scrolls the wheel at the flown-to site until the zoom slider reads `to` percent (the app switches to Mapbox on its own); `measure` refuses two points less than 60 CSS px apart on screen ("zoom in first"); `proximity` clicks the Proximity tab, "set on globe" and the place; the `measure` and `proximity` points are case-file place coordinates (plan C checks each against the verified case file); `filter` clicks a Filter panel mode (`country`, `category`, `source`; `age` is a slider without entries) and then the legend entry `label` (a click toggles it); `open_details` returns to the Search tab first; `toggle_layer` never takes the `Satellite` base map (any case: owner correction 2026-09-26, no satellite toggle in globe sections; satellite shows in the details page or a Mapbox take), refused before any side effect; `hud` lies in 0.5..2. Globe scenes: `flyto` (an `empire` must be a key of `EMPIRE_METADATA`); `places` (1-12 labelled places; a fixed pose fitted to the band, or a sweep of the camera longitude from `cam_lng_from` by `sweep_lng_deg` at `cam_lat` and `distance`); `distribution` (1-500 places, labels optional: one full turn of the whole globe, spec 4.10's world distribution, at a camera latitude from which one turn can show every place (a labelled place inside `PLACES_BAND`, a dot within the horizon less 5°); a set no latitude can show is refused before the take with `places [...] cannot face the camera in one turn of the globe; split the distribution`; the labelled places are case-file places drawn as pins, the unlabelled ones are the dots: plan C resolves the script's `site_ids` from the repo-root `public/data/sites/` export into `{id: <site id>, lat, lng}` and hands them over as unlabelled places, owner decision 15); the Mapbox fly-in and orbit. A Mapbox take's optional `country` is shown data (the recorder highlights that country's outline): plan C binds it to the site export's country of the case-file place at the take's `lat`/`lng`, and the recorder refuses a name the site's country table (`getCountryCode`) does not know with `unknown country <x>` before it prepares the map, so a take never silently lacks its highlight. Every scene refuses keys it does not know.

Events per kind: platform `pause_rotation`, `search`, `click_result`, `fly_wait`, `zoom`, `open_details`, `measure`, `measure_a`, `measure_b`, `toggle_layer`, `expand_layers`, `proximity`, `proximity_center`, `filter_mode`, `filter`, `wait` (clicks carry `x`/`y` in media pixels); globe `rotate`, `zoom`, `arrive` (`x`/`y` of the frame centre), `place` (`target`, `label` unless a distribution dot, `x`, `y` of its first frame, and `track`: its pixel `[x, y]` in every frame from the event to the end of the take, null while hidden or, for a labelled place, outside `PLACES_BAND`; the owner's rule is to project globe markers per frame, so pins follow the camera), `space`, `orbit`; source `page` (`url`, `title`: the page's own `<title>`, a record that nothing draws), `highlight` (`box` [x, y, w, h] image pixels, `target`); mapbox_topdown `pin` (`target`, `label`, `x`, `y`, `lat`, `lng`). Credits: platform and Mapbox takes `© Mapbox © OpenStreetMap © Maxar`; top-down `© Mapbox © Maxar` (satellite-v9) or the streets credit; our vector globe none; a source page `Source page: <host>` (the ASCII hostname SourceViewer draws, as `domainOf` does: IDNA, without `www.`), our paper page none (its anchor is `ev-` and two or more digits; a second id of a paragraph, an empty `span.theo-evidence-anchor` in plan B's HTML, outlines its paragraph). Place ids in specs are case-file place ids (a distribution's dots excepted: their ids are site ids, never cue targets), and a place or pin `label` is the case-file place's name; plan C checks each capture spec against the verified case file (place ids, names and coordinates, the `measure` and `proximity` points, the verified quote or `paper_anchor`) and a Mapbox take's `country` against the site export's country of its place. A top-down pin must fall in x 10-90 %, y 15-80 % of its frame and a labelled globe place in `PLACES_BAND` (x 12-78 %, y 15-74 %) at its event frame, so every label stays readable; the capture refuses anything else.

### D3. timeline.json as the renderer reads it (implements C8)

`parseTimeline` (`video/src/timeline.ts`) refuses, with the JSON path of the first defect: any unknown or missing key; `version` other than 1; `fps` other than 60; odd `width`/`height`; scenes that do not follow each other from frame 0 without gaps up to `durationInFrames`; an unknown `block`; props failing the block's registry schema; a cue outside its scene or with an unknown verb, a `status` value outside the claim statuses, a `meter` cue not targeting `"meter"` with two integers summing to 100, a `value` on any other verb; captions with an empty span, beyond the end or overlapping; ticker frames or counts that decrease; a first chapter not at frame 0 or chapters out of order; a credit for an unknown scene; `thumbnails` (owner decisions 24-25) other than exactly 3 entries `{frame, text}` with `frame` an integer inside the episode and `text` a teaser of 2-4 whitespace-separated words; a positive `gainDb`/`underNarrationDb`; any `src` not a clean relative path under `voice/`, `captures/`, `media/` or `music/`. All frame numbers are absolute; blocks receive scene-relative cues. `checkBlocks` then applies D1's cue-target rules, the end-card rule (a ShareCard only as the last scene), the brand-font rule (upper case included) to exactly D1's drawn strings (the blocks' `drawn` paths, the drawn strings of every capture prop, captions, credits, chapter titles and thumbnail teasers; owner decision 32) and each block's own checks (a clip long enough for its scene, markers inside their image, pins inside the frame, a platform zoom within the capture's pixels, globe tracks to the end of the take, meter start = 100, bar ranges with low < high, a ScaleZoom's 0 < small < large in a scene of at least 240 frames, diagram geometry, timeline years). Which frames make the three thumbnails and that they never show the answer is plan C's rule (its script validator); the renderer draws what `thumbnails` names. Which local verbs a block takes, which ids it shows, and that `introduce` needs a ClaimBoard listing the claim and `meter` needs a Meter scene are the renderer's `checkBlocks` rules; `lint.ts` enforces them through `loadTimeline` before bundling (the first render step), and plan C's `script.py` checks the same rules from the same table before voice and capture (its `LOCAL_CUES`), plus the brand-font rule, besides the case-file and props rules of C6/C8. The blocks' own checks run first in `loadTimeline` (plan C mirrors only clip length, map credits, marker boxes and the meter start); a failure there is fixed in the script props, without new voice or captures.

### D4. Node scripts (implements C9)

Run with `node --import tsx scripts/<name>.ts`, cwd `<repo>/video` (the form `test/scripts.test.ts` uses; plan C's `render.py` calls node directly, not the `npx.CMD` wrapper); every path flag is made absolute; unknown or missing flags, a missing timeline, a public dir lacking any referenced file or brand font, a failed block check, a render browser not on the NVIDIA, or any render error exit 1 with the message on stderr. Each script bundles into `bundle/` next to the public dir (`<episode>/render/bundle`, transient) and deletes it when it ends, on success and on failure: Remotion's `bundle()` copies the whole public dir into its output, and its default output, a fresh `%TEMP%` directory, is never deleted.

- `lint.ts --timeline <p> --public-dir <d> [--every 6] [--scale 0.5] [--report <json>] [--concurrency N]`: renders every 6th frame at half scale with `inputProps.lint = true` (no audio, clips not decoded), then each thumbnail candidate's teaser (the Thumbnail composition in lint mode, one frame each; its violations carry the candidate's episode frame and the id `thumbnail<K>:teaser`), prints each violation `{"type":"layout-violation","frame","a","b","reason"}` to stderr, exits 1 when there is at least one; `lint clean: N frames checked` otherwise (N = the episode frames plus the 3 thumbnails).
- `render.ts --timeline <p> --public-dir <d> --out <mp4> [--chunk-frames 3600] [--concurrency N]`: H.264 (`h264_nvenc`, GPU 0, 16 Mbit/s, no B-frames) + AAC 320k 48 kHz, BT.709, 60 fps; chunks of at most 3600 frames, each in a fresh browser, each writing its video (no B-frames) and its audio as a separate 16-bit PCM WAV (a 60 fps frame is exactly 800 samples at 48 kHz); the parts join by the ffmpeg concat demuxer, frame- and sample-exact; the joined audio is encoded to AAC 320k once here, and `pipeline/studio/render.py` re-encodes it once at 320k after the loudness gain; the frame count must equal the timeline's `durationInFrames`.
- `still.ts --timeline <p> --public-dir <d> --out-dir <dir> --candidate K [--frame N]` (owner decision 24; K is 1, 2 or 3): `thumbnail_<K>_3840.png` (3840x2160) and `thumbnail_<K>_1280.jpg` (1280x720, < 2 MB) of the Thumbnail composition for candidate K: the episode frame without captions, ticker or chapter tag; with the scene's in-frame credit line (spec 4.8), at the candidate's `frame` from `timeline.thumbnails`, or at `--frame N` (plan C's `episode thumbnail SLUG --candidate K --frame N`), with the candidate's teaser in the NERV heading type on its own dark glass, top left inside the title-safe area and clear of the bottom-right corner where YouTube lays its duration badge (owner decision 25). The credit line is that of the scene that shows the frame, bottom left in `THUMBNAIL_CREDIT_ZONE` (the episode's credit zone lies under the duration badge); a scene without credits gets none. One call renders one candidate; plan C calls it once per candidate.
- Each prints `gpu: <WebGL renderer>` for every browser it opens (the render log carries the proof).

The public dir holds every timeline `src` under its relative path plus the seven brand-font files `fonts/orbitron-600.woff2`, `fonts/orbitron-700.woff2`, `fonts/jetbrains-mono-400.woff2`, `fonts/jetbrains-mono-500.woff2`, `fonts/jetbrains-mono-400-latin-ext.woff2`, `fonts/cormorant-garamond-400-latin.woff2`, `fonts/cormorant-garamond-400-latin-ext.woff2` (plan C's render step links every `ancient-nerds-map/public/fonts/*.woff2`).

### D5. Frontend capture mode (spec 4.6)

`globe.html?demo=1&video=1&hud=1.3`: `?video=1` adds `body.video-mode` and a style that hides `.info-panel-top-right`, `.social-contribute-wrapper`, `.fps-display-container`, `.database-status-indicator`, `.connectors-status-indicator`, `.site-hover-tooltip:not(.selected-site-label)` (hover tooltips only: the selected site's label carries the same class and is the answer of a search moment), `.fps-warning-tooltip`, `.hardware-warning-banner` and the native cursor; `?hud=` (0.5-2, else an error) sets the HUD scale; `window.__VIDEO = {ready, hudScale}` turns `ready` true at globe_ready. Query string only, no browser storage. `window.__DEMO.screenPoint(lat, lng)` returns the viewport pixel of a place in the current view (Mapbox when shown, the globe camera otherwise) or null when hidden or off screen.

### D6. Recorder studio scenes

`npm run video:record -- <scene> --fps 60 --input <input.json> --out <dir>` with `studio-globe-flyto`, `studio-globe-places`, `studio-mapbox-flyin`, `studio-mapbox-orbit`; the input (written by `globe.py`, read through `STUDIO_SCENE_INPUT`) carries `scene`, `duration_s`, `frames_dir`, `renderer_path` and the scene's keys (places: `cam_lat`, `cam_lng`, `distance`, `sweep_lng_deg`, `places`, `points_path`; a flyto with a place also `places` and `points_path`; `globe.py`'s `distribution` is a places input with a sweep of 360). The scene writes `renderer.json` `{"renderer": ...}` first, then exactly `Math.round(duration_s * 60)` frames `f000000.jpg ...` (`globe.py` counts `floor(duration_s * 60 + 0.5)`, the same number), and, when the input names `points_path`, `points.json` `{place id: [[x, y] | null, ...]}` with one entry per frame, read from `window.__DEMO.screenPoint` after each frame.

## Where this plan and plan C meet (for the reconcile)

- **Cue rules (resolved in the reconcile).** D1's local cue column, the `BLOCKS` table of `video/src/blocks/index.ts`, is the single definition of which local verbs a block takes and which ids it shows (infographic element ids included: ScaleDrawing objects, UnitGrid groups, BarChart bars, Timeline events, Diagram elements, ListCard items, ScaleZoom's `small.id` and `large.id`). Plan C's `script.py` mirrors it as `LOCAL_CUES`, evaluated on each beat's resolved props, and adds the global rules `checkBlocks` applies (`introduce` needs a ClaimBoard of the episode listing the claim, a `meter` cue needs a Meter beat, cue keys `{frame, do, target, value?}` with `value` only on `status`/`meter`, meter values integers 0..100 summing to 100), so a script that passes `episode check` passes lint.ts's cue rules. `episode check` covers the cue, props-schema, reference and brand-glyph rules: plan C applies D1's brand-font rule (the code points the loaded latin and latin-ext files map: its verbatim copy of `DRAWABLE` of `video/src/theme/glyphs.ts`, tested against that file) to exactly D1's drawn strings before voice and capture: each beat block's `drawn` paths, read from `registry.json` (its `glyphs.drawn_strings`; no Python copy of the lists), the drawn strings of every `$capture` prop (its credits and `place`/`pin` labels; a `page` event's title is a record and never drawn), the hook caption tokens, the chapter titles, the credits (`visual.credit`, `Photo: <attribution> (<license>)`) and the thumbnail teasers (owner decision 32). The renderer's per-block semantic checks (the `check` functions of `video/src/blocks/index.ts`; plan C mirrors only clip length, map credits, marker boxes and the meter start) run in lint.ts's `loadTimeline`, which fails within seconds before bundling; fixing props never makes the voice stale. GlobeShot's `show` targets are the targets of the capture's labelled `place` events (`arrive` carries no label any more). GlobeShot takes a globe take of scene `flyto`, `places` or `distribution` (no credits) and MapboxFlyover one of scene `mapbox_flyin` or `mapbox_orbit` (the Mapbox credit): the renderer tells them apart by the capture's credits (`globe.CREDITS` is keyed by scene), plan C by the bound spec's `scene` at `episode check`. The former cross-stream request 8 is superseded and dropped.
- **Hook line budget, the end card and upper case (the same rule on both sides).** `video/src/captions.ts` exports the line budget on a line of its own, `export const HOOK_LINE_MAX_CHARS = 24`, and `captionLines` starts a new hook line before a word that would make the line longer than that (Task 10). Plan C's `script.py` mirrors the constant; its Task 27 reads this line with a regex, as it reads the glyph ranges. At `episode check`, before voice, `script.py` refuses a hook display token whose upper-case form, punctuation included, is longer than 24 characters: that is the one line no break can shorten. A ShareCard may only be the last scene (`checkBlocks`, Task 17), and plan C's `script.py` refuses a ShareCard on any beat but the last, in full episodes and slices alike. The brand-font rule covers every code point of a character's full upper-case mapping: `unsupportedChar` here and plan C's `glyphs.unsupported_char` with `str.upper()`. JavaScript and Python give the same mappings, e.g. `µ` to U+039C.
- **GPU (spec 4.11) is plan C's on its side.** Plan C's `doctor.py` (Task 26) probes the GPU with this plan's `pipeline.studio.capture.gpu` (`nvenc_problem()`, `remotion_browser(REPO / "video")`, `gpu_preference(exe)`, `chrome_renderer()` + `require_nvidia`) plus `nvidia-smi`, and `doctor --fix-gpu` calls `set_gpu_preference(exe)`; plan C's `voice.py` runs faster-whisper on `device="cuda", device_index=0` (float16) through `pipeline/video/shorts_captions.py`, which plan C owns; plan C's `render.py` stores the renderer string in the render ledger from the `gpu: <WebGL renderer>` lines render.ts prints to stdout, one per browser (that line format is the contract). The former cross-stream requests 5-7 now live in plan C.
- **Manifest events.** Spec 4.11 wants the renderer string in the capture manifest; C7 fixes the manifest keys, so it is the first event, `gpu`. Globe `place` events carry `track`. C's `manifest_problems` accepts both (events are `{t, name, ...}`), and refuses a manifest whose drawn strings (its `credits` and the `label` of `place`/`pin` events) fall outside D1's glyph rule, naming the capture; event names, targets, URLs, a `page` event's `title` (the page's own `<title>`, kept as a record) and the `gpu` label are not drawn and not checked (owner decision 32), so a source page with a non-latin title passes (plan C's `glyphs.DRAWN_EVENT_FIELDS` is `{"place": "label", "pin": "label"}`).
- **Thumbnails (owner decisions 24-25).** `timeline.json` carries `thumbnails: [{frame, text}]`, exactly 3: plan C compiles them from the script's `thumbnails: [{beat, at, text}]` and alone decides which frames may be used (never inside a twist, verdict or "what would change our mind" beat, never after the first verdict status or meter move) and which words (2-4, no verdict word). `still.ts --candidate K [--frame N]` renders one candidate as `thumbnail_<K>_3840.png` and `thumbnail_<K>_1280.jpg`; plan C calls it three times in `episode render` and once in `episode thumbnail SLUG --candidate K --frame N`, and packages the three JPEGs. `lint.ts` lints each teaser's layout. Each candidate carries the in-frame credit line of the scene that shows its frame (spec 4.8; the same JPEG is the paper page's poster), bottom left in `THUMBNAIL_CREDIT_ZONE`, so a thumbnail taken in a map or photo scene keeps its Mapbox/Maxar or photo credit; plan C's frame rule needs nothing extra for it.
- **The compiled timeline (C8 = D3), tested on both sides.** Plan C Task 21 commits `tests/pipeline/studio/golden_timeline.json`, its compiler's output for its fixture episode, and keeps it current; this plan's Task 37 parses that same file (`video/test/contract.test.ts`: `parseTimeline`, `checkBlocks`, 60 fps, upper-case hook captions), so a drift on either side fails a suite before the first real render.
- **Contract C9.** `render.ts` writes H.264 + AAC 320k, BT.709 limited range (`color_range=tv`: black decodes to Y 16, the NERV background to Y 28), so plan C's `normalize_loudness` (`-c:v copy`, re-encoding the audio once at 320k) and `render_audit` (1920x1080, 60 fps, exact frame count, the black-frame threshold on the limited range) work on it. The renderer animates entrances and cues only, so cards, stills and infographics are static by design: plan C's frozen-frame audit covers clip scenes only (a capture with a non-null `fps`), and a clip that holds one picture for more than 4 s is refused by it, so the script cuts to a card instead. The node scripts run as `node --import tsx scripts/<name>.ts` with cwd `video/`; `render/bundle/` is transient (created and removed by each script).
- **Props bound to the case file (plan C's checks; D's BarChart prints exact values).** D's schemas describe resolved values (C6); plan C refuses inline entities in the script (`image`, `evidence` and `claims[]` must be `{"$ref"}`, `clip`, `map` and `page` must be `{"$capture"}`), binds every capture spec to the verified case file (place ids, names and coordinates, including the labelled `places` of a globe `distribution` take, whose dots are site ids plan C resolves from the repo-root `public/data/sites/` export, owner decision 15; the `measure` and `proximity` points of a platform take; the verified quote or `paper_anchor`; a Mapbox take's optional `country`, which must equal the site export's `c` of the case-file place at its `lat`/`lng`, a place with a `site_id`), applies the one quantity rule (a BarChart bar or a ScaleZoom quantity, `small` or `large`, whose `id` is a case-file quantity id shows that quantity: its `value` equals the quantity's value, a range as `[low, high]` in a BarChart only, and the chart's `unit` equals the quantity's `unit`; no other props element may use a quantity id; BarChart draws a range as a range and both blocks print every value with its own decimals, `decimalsOf`), and validates each claim's icon against the ClaimBoard icon enum of `registry.json`. A claim's resolved `status` is what the board shows before its first `status` cue (normally `pending`); verdicts come only from `status` cues. Place and quantity stay resolvable (`resolved()`) because their ids are cue and pin targets, but no scene block takes them as a prop value.

---

## File Structure

Created (all owned by this plan):

| File | Responsibility |
|---|---|
| `video/package.json`, `video/package-lock.json` | The renderer package: Remotion 4.0.529 and every other dependency pinned exactly; scripts `registry`, `typecheck`, `test`, `test:gpu`, `studio`, `lint:layout`, `render`, `still`. |
| `video/tsconfig.json`, `video/vitest.config.ts`, `video/remotion.config.ts` | Strict TypeScript over src, scripts and tests; vitest in node; settings for `npm run studio` only. |
| `video/src/index.ts`, `video/src/Root.tsx` | Registers the Episode and Thumbnail compositions; calculateMetadata validates the timeline, measures audio and images and proves the GPU. |
| `video/src/Episode.tsx`, `video/src/SceneView.tsx`, `video/src/Thumbnail.tsx` | One Sequence per scene, the overlays, narration clips and the ducked music; lint mode; a thumbnail candidate's frame with its teaser and its scene's credit line. |
| `video/src/gpu.ts` | The render browser's WebGL renderer string. |
| `video/src/timeline.ts`, `video/src/schema.ts` | timeline.json parsing (D3, with the three thumbnail candidates); the JSON-schema subset validator of the registry. |
| `video/src/state.ts`, `video/src/cues.ts`, `video/src/context.ts`, `video/src/media.ts` | Episode-wide claim and meter state; scene cue helpers; the episode context; audio length and image size measurement. |
| `video/src/audio.ts`, `video/src/captions.ts`, `video/src/format.ts` | Narration spans and music ducking; hook caption lines, ticker and credit merging; distance, year, number and probability formatting. |
| `video/src/theme/colors.ts`, `fonts.ts`, `glyphs.ts`, `type.ts` | NERV palette (mirror of the site tokens and the brand red, checked against the site files), brand fonts from the public dir (latin and latin-ext; `brandFontsReady()` resolves once every face is in), the code points their files map (`DRAWABLE`, generated), text styles. |
| `video/src/motion/index.ts` | Frame-driven NERV motion (crtOpen, bootIn, borderTrace, typeOn, digitRoll, stampSlam, ringPulse, sweep); no flicker. |
| `video/src/layout/zones.ts`, `geometry.ts`, `transform.ts` | Screen zones (safe area, YouTube controls); the pure overlap checker; image-to-screen math for moving markers. |
| `video/src/layout/LayoutBox.tsx`, `LayoutGuard.tsx` | Box registration in lint mode, measured only once the brand fonts are in (the lint-mode provider holds the frame with `delayRender` until then); the reporter that prints one JSON line per violation. |
| `video/src/blocks/types.ts`, `icons.tsx`, `schemas.ts`, `registry.json`, `index.ts`, `clips.ts` | Block props types (C6), ClaimBoard icons, the registry source with each block's drawn prop paths and its generated JSON (C5), the block table, cue rules and the drawn-string glyph check, clip rules. |
| `video/src/blocks/*.tsx` (27 files besides `icons.tsx`) | Panel, Stamp, LowerThird, CreditLine, ChapterTag, Ticker, HookCaptions, Footage, ImageLayer and the 18 scene blocks of D1. |
| `video/src/fixtures/demo-timeline.json`, `demo.ts` | The graphics-only demo timeline (all 12 graphics blocks, a BarChart range, the three thumbnail candidates): default props for `npm run studio`, the test fixture and Task 22's demo render. |
| `video/scripts/args.ts`, `cli.ts`, `registry.ts`, `lint.ts`, `render.ts`, `still.ts` | Script helpers (flags, chunks, violation lines, GPU rules, the bundle dir), shared plumbing (bundling next to the public dir and removing it), the registry writer and the three C9 scripts. |
| `video/scripts/fontCoverage.ts`, `glyphs.ts` | The brand font files' cmaps (a WOFF2 reader on Node's brotli) and the drawable set computed from them; the printer of `glyphs.ts` `DRAWABLE`. |
| `video/test/*.test.ts` (25 files), `video/test/fixtures/smoke-timeline.json` | vitest suites and the 10-second smoke timeline; `contract.test.ts` (Task 37) parses plan C's committed golden `tests/pipeline/studio/golden_timeline.json`. |
| `video/test/gpu/vitest.config.ts`, `guard.gpu.ts`, `guardFixture.tsx` | The real-browser layout-lint check (Task 11), workstation only: `npm run test:gpu` renders planted violations in Remotion's Chrome on the RTX 3080 with the brand fonts arriving late. `npm test` collects only `*.test.ts`, so CI never runs it. |
| `pipeline/studio/capture/__init__.py` | The four C7 functions. |
| `pipeline/studio/capture/manifest.py` | Manifest shape and validation, events (tracks included), credits, `CaptureError`, typed spec values, failed-tool messages. |
| `pipeline/studio/capture/gpu.py` | NVIDIA proof, Chrome GPU flags, NVENC availability, the Remotion browser's Windows GPU preference, the doctor's Chrome renderer probe. |
| `pipeline/studio/capture/encode.py` | Frames to constant-rate HEVC clips on NVENC. |
| `pipeline/studio/capture/projection.py` | Web-Mercator and globe-camera projection (pure). |
| `pipeline/studio/capture/vite.py` | Token, tools, the awake display, the local Vite server, the analytics tracker the captures block. |
| `pipeline/studio/capture/mapbox.py` | Mapbox Static top-down frames with projected pins. |
| `pipeline/studio/capture/sources.py`, `highlight.js` | Source-page and paper-page captures with the quote highlighted (slug and evidence-id checks imported from plans C and A). |
| `pipeline/studio/capture/platform.py`, `nerv_cursor.js` | Platform takes of the real site with the fast NERV cursor. |
| `pipeline/studio/capture/globe.py` | Globe and Mapbox takes through the recorder (fly-to, places with a fixed pose or a sweep, the world distribution), per-frame place tracks. |
| `tests/pipeline/studio/capture/__init__.py`, `test_capture_*.py` (10 files) | Capture tests. |
| `ancient-nerds-map/src/utils/videoMode.ts`, `__tests__/videoMode.test.ts` | `?video=1` capture mode (D5). |
| `ancient-nerds-map/src/utils/screenPoint.ts`, `__tests__/screenPoint.test.ts` | Pixel of a place in the current view. |
| `ancient-nerds-map/video/scenes/studio-frames.ts`, `studio-globe.ts`, `studio-mapbox.ts`, `__tests__/studio-scenes.test.ts` | Exact frame grabbing, per-frame place tracking and the four studio scenes (D6). |

Modified: `ancient-nerds-map/src/App.tsx` (video mode effect, ready flag), `ancient-nerds-map/src/components/Globe.tsx` (HUD scale from `?hud=`, `screenPoint`), `ancient-nerds-map/src/utils/demoApi.ts` (`screenPoint` in DemoAPI and GlobeDemoRefs), `ancient-nerds-map/video/record.ts` (studio scenes registered, `grabsFrames`, `STUDIO_SCENE_INPUT`, `screenPoint` proxy, Vite on a strict port), `ancient-nerds-map/video/scenes/site-short.ts` (exports `SiteInput`, `prepareMapbox`, `warmPath` for the studio scenes; no behaviour change).

Deleted (the dead weekly composition, never rendered): `video/src/WeeklyVideo.tsx`, `video/src/types.ts`, `video/src/utils/timing.ts`, `video/src/components/Globe3D.tsx`, `KenBurns.tsx`, `LowerThird.tsx`, `video/src/compositions/ClipWithAttribution.tsx`, `GlobeFlyTo.tsx`, `IntroSequence.tsx`, `OutroSequence.tsx`, `StorySegment.tsx`, `TransitionWipe.tsx` (`Root.tsx`, `index.ts`, `package.json`, `package-lock.json`, `tsconfig.json`, `remotion.config.ts` are rewritten).

---

### Task 1: Replace the weekly Remotion project with the pinned studio renderer package

**Files:**
- Delete: the 14 files under `video/src/` (the weekly composition, never rendered)
- Rewrite: `video/package.json`, `video/tsconfig.json`, `video/remotion.config.ts`, `video/package-lock.json` (by `npm install`)
- Create: `video/vitest.config.ts`
- Test: `video/test/project.test.ts`

- [ ] **Step 1: Remove the weekly composition and write the failing test**

```bash
git rm -q video/src/Root.tsx video/src/WeeklyVideo.tsx video/src/index.ts video/src/types.ts video/src/utils/timing.ts video/src/components/Globe3D.tsx video/src/components/KenBurns.tsx video/src/components/LowerThird.tsx video/src/compositions/ClipWithAttribution.tsx video/src/compositions/GlobeFlyTo.tsx video/src/compositions/IntroSequence.tsx video/src/compositions/OutroSequence.tsx video/src/compositions/StorySegment.tsx video/src/compositions/TransitionWipe.tsx
```

**`video/test/project.test.ts`** (complete file):

```ts
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const read = (name: string) => JSON.parse(readFileSync(fileURLToPath(new URL(`../${name}`, import.meta.url)), 'utf-8'))
const pkg = read('package.json') as { dependencies: Record<string, string>; devDependencies: Record<string, string> }
const deps = { ...pkg.dependencies, ...pkg.devDependencies }
const isRemotion = (name: string) => name === 'remotion' || name.startsWith('@remotion/')

describe('video/package.json (spec 4.8: Remotion 4.0.529, every @remotion/* at the same exact version)', () => {
  it('declares remotion and the five @remotion packages the renderer uses, all at exactly 4.0.529', () => {
    const remotion = Object.keys(deps).filter(isRemotion).sort()
    expect(remotion).toEqual(['@remotion/bundler', '@remotion/cli', '@remotion/fonts', '@remotion/media', '@remotion/renderer', 'remotion'])
    for (const name of remotion) expect(deps[name], name).toBe('4.0.529')
  })
  it('pins every other dependency to an exact version', () => {
    for (const [name, version] of Object.entries(deps)) expect(version, name).toMatch(/^\d+\.\d+\.\d+$/)
  })
  it('locks every installed remotion package, transitive ones included, at 4.0.529', () => {
    const lock = read('package-lock.json') as { packages: Record<string, { version?: string }> }
    const locked = Object.entries(lock.packages).filter(([key]) => isRemotion(key.replace(/^.*node_modules\//, '')))
    expect(locked.length).toBeGreaterThan(6)
    for (const [key, entry] of locked) expect(entry.version, key).toBe('4.0.529')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx --yes vitest@4.0.18 run test/project.test.ts`
Expected: FAIL — the old `package.json` declares `@remotion/cli`, `@remotion/three` and `remotion` as `^4.0.0` and no `@remotion/media`, so the first test reports the wrong package list and the version tests fail.

- [ ] **Step 3: Implement**

**`video/package.json`** (complete file):

```json
{
  "name": "ancient-nerds-studio-video",
  "version": "2.0.0",
  "private": true,
  "description": "Studio renderer: timeline.json (pipeline/studio/timeline.py) -> NERV long-form episode, layout lint and thumbnails",
  "type": "module",
  "scripts": {
    "studio": "remotion studio src/index.ts --public-dir ../ancient-nerds-map/public",
    "registry": "tsx scripts/registry.ts",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:gpu": "vitest run --config test/gpu/vitest.config.ts",
    "lint:layout": "tsx scripts/lint.ts",
    "render": "tsx scripts/render.ts",
    "still": "tsx scripts/still.ts"
  },
  "dependencies": {
    "@remotion/bundler": "4.0.529",
    "@remotion/cli": "4.0.529",
    "@remotion/fonts": "4.0.529",
    "@remotion/media": "4.0.529",
    "@remotion/renderer": "4.0.529",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "remotion": "4.0.529"
  },
  "devDependencies": {
    "@types/node": "22.19.1",
    "@types/react": "18.3.27",
    "tsx": "4.20.6",
    "typescript": "5.9.3",
    "vitest": "4.0.18"
  }
}
```

`test` runs the suites every machine can run (`test/**/*.test.ts`, the CI job `lint-video`). `test:gpu` runs the real-browser checks under `test/gpu/` (`*.gpu.ts`, own config, added by Task 11), which render in Remotion's Chrome on the RTX 3080 and so run on the workstation only.

**`video/tsconfig.json`** (complete file):

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "types": ["node"]
  },
  "include": ["src/**/*", "scripts/**/*", "test/**/*", "remotion.config.ts", "vitest.config.ts"]
}
```

**`video/vitest.config.ts`** (complete file):

```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    environment: 'node',
  },
})
```

**`video/remotion.config.ts`** (complete file):

```ts
import { Config } from '@remotion/cli/config'

// Settings for `npm run studio` (the preview) only: scripts/render.ts, lint.ts
// and still.ts pass every render option explicitly.
Config.setVideoImageFormat('jpeg')
Config.setOverwriteOutput(true)
```

Install (writes a new `package-lock.json`; `node_modules/` is gitignored) and fetch Remotion's pinned Chrome Headless Shell into `node_modules/.remotion`:

```bash
cd video && rm -f package-lock.json && npm install --no-audit --no-fund && npx remotion browser ensure
```

Expected: `added 294 packages` (the count may differ by a few transitive packages), then the headless shell download ending at `113.3 Mb/113.3 Mb` (or nothing when it is already there).

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/project.test.ts`
Expected: `Tests  3 passed (3)`

- [ ] **Step 5: Commit**

```bash
git add video/package.json video/package-lock.json video/tsconfig.json video/vitest.config.ts video/remotion.config.ts video/test/project.test.ts
git commit -m "Replace the never-rendered weekly Remotion project with the studio renderer package pinned to Remotion 4.0.529" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: NERV theme and frame-driven motion

**Files:**
- Create: `video/src/theme/colors.ts`, `video/src/theme/fonts.ts`, `video/src/theme/glyphs.ts`, `video/src/theme/type.ts`, `video/src/motion/index.ts`, `video/scripts/fontCoverage.ts`, `video/scripts/glyphs.ts`
- Test: `video/test/motion.test.ts`, `video/test/colors.test.ts`, `video/test/glyphs.test.ts`

The motion is the renderer's port of `ancient-nerds-map/src/styles/nerv-animations.css`: crt-open, boot-in, border-trace, type-on, digit-roll, the stamp slam, ring-pulse and sweep, each a pure function of the frame. Flicker, glitch and every alert/emergency flash are left out on purpose (owner rule: no flicker). The palette mirrors `ancient-nerds-map/src/styles/tokens.css` and the brand red `UI_COLORS.primary` of `src/constants/colors.ts` (spec 4.8); `colors.test.ts` reads both site files and fails when a mirrored value drifts. The fonts are the site's own woff2 files, loaded from the per-render public dir through `@remotion/fonts` (which holds the render with `delayRender` until each file loaded and cancels it when one is missing; that hold does not stop Remotion from mounting the composition, and so laying out its first frame, before the files arrive, so `loadBrandFonts()` keeps the promise of all eight faces and `brandFontsReady()` returns it, for Task 11's lint mode, which measures text only in the brand fonts): the latin files plus the latin-ext files of JetBrains Mono and Cormorant Garamond, each with the `unicode-range` of `ancient-nerds-map/public/fonts/fonts.css`, so transliterations (Vinča, Enūma Eliš, Mahābhārata) draw in the brand fonts. `glyphs.ts` holds those two ranges for `fonts.ts`, but a range only decides which face Chrome tries for a character, not whether that face has it: Google's subset files leave gaps in their declared range, and Chrome draws such a character in a Windows system font without an error (review fix 2026-09-27, measured in Remotion's chrome-headless-shell with CDP `CSS.getPlatformFontsForNode`: `Ḫattuša` drew its `Ḫ` in Arial in a heading and in Courier New in body text). JetBrains Mono latin-ext maps, of U+1E00-1EFF, only `ẀẁẂẃẄẅẞỲỳỴỵỶỷỸỹ`: no `Ḫ Ḥ Ṣ Ṭ Ṛ Ṃ Ṇ Ḍ Ṯ Ḏ Ẓ`, no `ʾ ʿ`; its latin file has no U+2010-2012, U+2015, U+2021, `‰` or `‼`. So the rule's set is `DRAWABLE`, generated from the files themselves by `scripts/fontCoverage.ts` (each loaded face's cmap, read with Node's own brotli, within the face's unicode-range; the part common to the three stacks of `type.ts`, heading, body/hud and serif, which is JetBrains Mono's and Cormorant Garamond's common part; plus tab, line feed and carriage return, which CSS lays out as white space). `glyphs.test.ts` recomputes it from `ancient-nerds-map/public/fonts` and fails on drift; `npx tsx scripts/glyphs.ts` prints the new constant. Task 17's `checkBlocks` refuses any character outside `DRAWABLE`. `heading()` and `hud()` set `textTransform: 'uppercase'`, and the browser then draws the full Unicode upper-case mapping. So a character counts as drawable only when it and every code point of its upper case lie in `DRAWABLE`. Example: `ƒ` (U+0192, drawable) draws as `Ƒ` (U+0191), which no loaded file maps; the error names the written character and what it turns into. `µ`, `ǰ` and `ẖ` are refused as written (no loaded file maps them). Plan C's `glyphs.unsupported_char` applies the same rule with `str.upper()`, which gives the same mappings, on its verbatim copy of `DRAWABLE`. Orbitron ships latin only (`ancient-nerds-map/public/fonts/` has no Orbitron latin-ext file), so `HEADING` names JetBrains Mono second: a latin-ext letter in a heading (Şanlıurfa, Enūma Eliš) is drawn, per character, by the loaded JetBrains Mono latin-ext face. Hittite, Egyptian, Sanskrit and Semitic transliterations (`Ḫattuša`, `Ḥatḥor`, `Kṛṣṇa`, `Baʿal`) are refused until the owner decides on a font that has them (owner question Q14).

- [ ] **Step 1: Write the failing test**

**`video/test/motion.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { bootIn, borderTrace, crtOpen, digitRoll, progress, ringPulse, stampSlam, sweep, typeOn } from '../src/motion'

describe('NERV motion is a pure function of the frame', () => {
  it('progress clamps to 0..1', () => {
    expect(progress(-5, 0, 10)).toBe(0)
    expect(progress(10, 0, 10)).toBe(1)
    expect(progress(99, 0, 10)).toBe(1)
  })
  it('crt-open stays a line for 40 % of its 24 frames, then opens fully', () => {
    expect(crtOpen(0, 10)).toEqual({ opacity: 0 })
    expect(String(crtOpen(15, 10).transform)).toBe('scaleY(0.002)')
    expect(crtOpen(40, 10)).toEqual({ opacity: 1, transform: 'scaleY(1)', filter: 'brightness(1)' })
  })
  it('boot-in fades, rises and settles its brightness', () => {
    expect(bootIn(0, 0, 30).opacity).toBe(0)
    expect(bootIn(30, 0, 30)).toEqual({ opacity: 1, transform: 'translateY(0px)', filter: 'brightness(1)' })
    expect(bootIn(30, 0, 30, 'translateX(-50%)').transform).toBe('translateX(-50%) translateY(0px)')
  })
  it('border-trace draws the outline in', () => {
    expect(borderTrace(0, 0, 20, 400)).toBe(400)
    expect(borderTrace(20, 0, 20, 400)).toBe(0)
  })
  it('type-on reveals characters at the set rate', () => {
    expect(typeOn('EVIDENCE', 4, 5)).toBe('')
    expect(typeOn('EVIDENCE', 5, 5, 2)).toBe('EV')
    expect(typeOn('EVIDENCE', 50, 5, 2)).toBe('EVIDENCE')
  })
  it('digit-roll lands exactly on the target', () => {
    expect(digitRoll(0, 80, 0, 0, 30)).toBe(0)
    expect(digitRoll(0, 80, 30, 0, 30)).toBe(80)
    expect(digitRoll(50, 15, 100, 0, 30)).toBe(15)
  })
  it('the stamp settles at scale 1', () => {
    expect(stampSlam(0, 10, 60)).toEqual({ opacity: 0 })
    const settled = String(stampSlam(200, 10, 60).transform)
    expect(settled.startsWith('rotate(-6deg) scale(')).toBe(true)
    expect(Number(settled.slice('rotate(-6deg) scale('.length, -1))).toBeCloseTo(1, 6)
  })
  it('ring-pulse repeats every period and fades out, never blinks', () => {
    expect(ringPulse(10, 10, 60)).toEqual(ringPulse(70, 10, 60))
    expect(ringPulse(10, 10, 60)).toEqual({ scale: 0.8, opacity: 0.6 })
    expect(ringPulse(40, 10, 60).opacity).toBeCloseTo(0.3)
  })
  it('sweep crosses once', () => {
    expect(sweep(0, 0, 40)).toBe(0)
    expect(sweep(40, 0, 40)).toBe(1)
  })
})
```

**`video/test/colors.test.ts`** (complete file):

```ts
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { MIRROR, colors } from '../src/theme/colors'

/** A file of the frontend, read as text (the site is the source of every mirrored colour). */
const site = (rel: string) => readFileSync(fileURLToPath(new URL(`../../ancient-nerds-map/src/${rel}`, import.meta.url)), 'utf-8')
const TOKENS = site('styles/tokens.css')
const CONSTANTS = site('constants/colors.ts')

describe('the NERV palette mirrors the site (spec 4.8)', () => {
  it.each(MIRROR.map((m) => [m.key, m] as const))('%s', (_key, m) => {
    const hex = colors[m.key]
    if ('token' in m) expect(TOKENS).toContain(`${m.token}: ${hex};`)
    else expect(CONSTANTS).toContain(`${m.constant}: '${hex}'`)
  })
  it('mirrors every hex colour of the palette but white', () => {
    const hexKeys = Object.entries(colors)
      .filter(([key, value]) => key !== 'white' && /^#[0-9a-f]{6}$/i.test(value))
      .map(([key]) => key)
    expect(MIRROR.map((m) => m.key).sort()).toEqual(hexKeys.sort())
  })
})
```

**`video/test/glyphs.test.ts`** (complete file):

```ts
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { SITE_PUBLIC_DIR, drawableRange, formatUnicodeRange, woff2Cmap } from '../scripts/fontCoverage'
import { FONTS, FONT_FILES, HEADING } from '../src/theme/fonts'
import { DRAWABLE, LATIN_EXT_RANGE, LATIN_RANGE, glyphReason, parseUnicodeRange, unsupportedChar } from '../src/theme/glyphs'

const cmap = (file: string) => woff2Cmap(join(SITE_PUBLIC_DIR, 'fonts', file))

describe('the brand fonts draw only the code points their files map (DRAWABLE)', () => {
  it('parses and formats a CSS unicode-range', () => {
    expect(parseUnicodeRange('U+0000-00FF, U+0131, U+A720-A7FF')).toEqual([
      [0x0, 0xff],
      [0x131, 0x131],
      [0xa720, 0xa7ff],
    ])
    expect(formatUnicodeRange([0x131, 0x20, 0x21, 0x22, 0xa0])).toBe('U+0020-0022, U+00A0, U+0131')
  })
  it('reads each woff2 cmap as fontTools 4.65 does (glyph counts measured 2026-09-27)', () => {
    const counts = Object.fromEntries(FONT_FILES.map((file) => [file, cmap(file.slice('fonts/'.length)).size]))
    expect(counts).toEqual({
      'fonts/orbitron-600.woff2': 183,
      'fonts/orbitron-700.woff2': 183,
      'fonts/jetbrains-mono-400.woff2': 229,
      'fonts/jetbrains-mono-400-latin-ext.woff2': 190,
      'fonts/jetbrains-mono-500.woff2': 229,
      'fonts/cormorant-garamond-400-latin.woff2': 229,
      'fonts/cormorant-garamond-400-latin-ext.woff2': 306,
    })
    // the gaps Google's subsets leave in their declared range: ẞ is there, Ḫ and the non-breaking hyphen are not
    expect(cmap('jetbrains-mono-400-latin-ext.woff2').has(0x1e9e)).toBe(true)
    expect(cmap('jetbrains-mono-400-latin-ext.woff2').has(0x1e2a)).toBe(false)
    expect(cmap('jetbrains-mono-400.woff2').has(0x2011)).toBe(false)
    expect(cmap('cormorant-garamond-400-latin-ext.woff2').has(0x1e2a)).toBe(true)
  })
  it('DRAWABLE is what the loaded files map, recomputed from ancient-nerds-map/public/fonts (npx tsx scripts/glyphs.ts prints it)', () => {
    expect(DRAWABLE).toBe(drawableRange())
  })
  it('accepts the transliterations the files map and layout white space', () => {
    for (const text of ['Vinča', 'Enūma Eliš', 'Mahābhārata', 'Çatalhöyük', 'Şanlıurfa', 'Ħal Saflieni', 'ÿ ß ſ ŉ', '1,000–1,650 t × 2 — “quoted” …', 'one\ntwo\tthree'])
      expect(unsupportedChar(text), text).toBeNull()
  })
  it('refuses other scripts, the gaps of the subsets and letters whose upper case leaves the fonts', () => {
    expect(unsupportedChar('Κνωσός')).toBe('Κ')
    expect(unsupportedChar('Baalbek → Rome')).toBe('→')
    // inside the declared latin-ext and latin ranges, but in no loaded file: a system font would draw them
    expect(unsupportedChar('Ḫattuša')).toBe('Ḫ')
    expect(unsupportedChar('Kṛṣṇa')).toBe('ṛ')
    expect(unsupportedChar('Ḥatḥor')).toBe('Ḥ')
    expect(unsupportedChar('Baʿal')).toBe('ʿ')
    expect(unsupportedChar('non‑breaking')).toBe('‑')
    expect(unsupportedChar('5‰')).toBe('‰')
    expect(unsupportedChar('Smaller than 1 µm?')).toBe('µ')
    expect(unsupportedChar('ẖ')).toBe('ẖ')
    // heading() and hud() draw upper case: "ƒ" becomes "Ƒ", which no loaded file maps
    expect(unsupportedChar('ƒ')).toBe('ƒ')
    expect(glyphReason('ƒ')).toBe('"ƒ" (U+0192) draws as "Ƒ" (U+0191) in upper case, which has no glyph in the brand fonts (latin and latin-ext only)')
    expect(glyphReason('Ḫ')).toBe('"Ḫ" (U+1E2A) has no glyph in the brand fonts (latin and latin-ext only)')
    expect(glyphReason('Κ')).toBe('"Κ" (U+039A) has no glyph in the brand fonts (latin and latin-ext only)')
  })
  it('loads a latin-ext file next to the latin files of JetBrains Mono and Cormorant Garamond', () => {
    const faces = (range: string) =>
      FONTS.filter((f) => f.unicodeRange === range)
        .map((f) => `${f.family} ${f.weight}`)
        .sort()
    expect(faces(LATIN_EXT_RANGE)).toEqual(['Cormorant Garamond 400', 'JetBrains Mono 400', 'JetBrains Mono 500'])
    expect(faces(LATIN_RANGE)).toEqual(['Cormorant Garamond 400', 'JetBrains Mono 400', 'JetBrains Mono 500', 'Orbitron 600', 'Orbitron 700'])
    expect(FONT_FILES).toHaveLength(7)
    // Orbitron has no latin-ext file: a heading falls back per character to JetBrains Mono, whose files DRAWABLE reflects
    expect(HEADING.split(',')[1].trim()).toBe("'JetBrains Mono'")
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/motion.test.ts test/colors.test.ts test/glyphs.test.ts`
Expected: FAIL, all three files, with `Error: Cannot find module '../src/motion' imported from '.../video/test/motion.test.ts'` and the same for `../src/theme/colors` and `../src/theme/fonts`.

- [ ] **Step 3: Implement**

**`video/src/theme/colors.ts`** (complete file):

```ts
/**
 * NERV palette of the renderer: a mirror of the site's design tokens
 * (ancient-nerds-map/src/styles/tokens.css, `--_palette-*`) and of the brand red
 * (UI_COLORS.primary, ancient-nerds-map/src/constants/colors.ts), so video frames
 * and the site read as one product. Change a colour on the site first, then here:
 * test/colors.test.ts reads both site files and fails on any drift (MIRROR).
 */
export const colors = {
  bg: '#0a0e14', // --_palette-dark-900 (--surface-page)
  bgPanel: 'rgba(10, 18, 16, 0.88)', // --_palette-dark-850 at panel opacity
  green: '#00cc66', // --_palette-green-bright (--accent-primary)
  greenDim: '#2a5a2a', // --_palette-green-700 (--crt-700)
  crt300: '#b0d0b0', // --_palette-green-300 (--text-secondary)
  crt400: '#6ab06a', // --_palette-green-400 (--text-muted)
  cyan: '#00c8c8', // --_palette-cyan-500 (--accent-secondary)
  amber: '#fbbf24', // --_palette-amber-400 (--accent-amber)
  orange: '#f59e0b', // --_palette-orange-500 (--status-warning)
  red: '#ef4444', // --_palette-red-error (--status-error)
  okGreen: '#22c55e', // --_palette-status-green (--status-ok)
  brandRed: '#c02023', // UI_COLORS.primary (src/constants/colors.ts)
  white: '#ffffff',
  text: '#e0e0e0', // --_palette-neutral-50 (--text-body)
  muted: '#787878', // --_palette-neutral-300
} as const

type ColorKey = keyof typeof colors

/** Where each mirrored hex colour lives on the site: a tokens.css variable or a UI_COLORS key. */
export const MIRROR: readonly ({ key: ColorKey; token: string } | { key: ColorKey; constant: string })[] = [
  { key: 'bg', token: '--_palette-dark-900' },
  { key: 'green', token: '--_palette-green-bright' },
  { key: 'greenDim', token: '--_palette-green-700' },
  { key: 'crt300', token: '--_palette-green-300' },
  { key: 'crt400', token: '--_palette-green-400' },
  { key: 'cyan', token: '--_palette-cyan-500' },
  { key: 'amber', token: '--_palette-amber-400' },
  { key: 'orange', token: '--_palette-orange-500' },
  { key: 'red', token: '--_palette-red-error' },
  { key: 'okGreen', token: '--_palette-status-green' },
  { key: 'text', token: '--_palette-neutral-50' },
  { key: 'muted', token: '--_palette-neutral-300' },
  { key: 'brandRed', constant: 'primary' },
]

export type Tone = 'accent' | 'info' | 'warn' | 'alert' | 'muted'

export const TONES: readonly Tone[] = ['accent', 'info', 'warn', 'alert', 'muted']

export const toneColor: Record<Tone, string> = {
  accent: colors.green,
  info: colors.cyan,
  warn: colors.amber,
  alert: colors.red,
  muted: colors.muted,
}

/** Claim statuses of the case file (pipeline/studio/casefile.py CLAIM_STATUSES). */
export type ClaimStatus = 'pending' | 'supported' | 'weakened' | 'refuted' | 'open'

export const CLAIM_STATUSES: readonly ClaimStatus[] = ['pending', 'supported', 'weakened', 'refuted', 'open']

export const statusColor: Record<ClaimStatus, string> = {
  pending: colors.muted,
  supported: colors.okGreen,
  weakened: colors.orange,
  refuted: colors.red,
  open: colors.cyan,
}
```

**`video/src/theme/fonts.ts`** (complete file):

```ts
/**
 * Brand fonts from the per-render public dir. pipeline/studio/render.py links
 * every ancient-nerds-map/public/fonts/*.woff2 into <episode>/render/public/fonts;
 * `npm run studio` points --public-dir at ancient-nerds-map/public directly.
 * loadFont() holds the render (delayRender) until each file is loaded and fails
 * it when a file is missing; scripts/cli.ts checks the files before Chrome starts.
 *
 * Each face carries the unicode-range of the site's fonts.css (glyphs.ts): the
 * latin files, plus the latin-ext files of JetBrains Mono (both weights share the
 * 400 file, as on the site) and Cormorant Garamond. Orbitron ships latin only, so
 * HEADING names JetBrains Mono second: a latin-ext character of a heading is drawn
 * by the JetBrains Mono latin-ext face when that file maps it. glyphs.ts DRAWABLE
 * admits only the characters the loaded files map, so no drawn string reaches a
 * system font.
 */
import { loadFont } from '@remotion/fonts'
import { staticFile } from 'remotion'

import { LATIN_EXT_RANGE, LATIN_RANGE } from './glyphs'

export const FONTS = [
  { family: 'Orbitron', file: 'fonts/orbitron-600.woff2', weight: '600', unicodeRange: LATIN_RANGE },
  { family: 'Orbitron', file: 'fonts/orbitron-700.woff2', weight: '700', unicodeRange: LATIN_RANGE },
  { family: 'JetBrains Mono', file: 'fonts/jetbrains-mono-400.woff2', weight: '400', unicodeRange: LATIN_RANGE },
  { family: 'JetBrains Mono', file: 'fonts/jetbrains-mono-400-latin-ext.woff2', weight: '400', unicodeRange: LATIN_EXT_RANGE },
  { family: 'JetBrains Mono', file: 'fonts/jetbrains-mono-500.woff2', weight: '500', unicodeRange: LATIN_RANGE },
  { family: 'JetBrains Mono', file: 'fonts/jetbrains-mono-400-latin-ext.woff2', weight: '500', unicodeRange: LATIN_EXT_RANGE },
  { family: 'Cormorant Garamond', file: 'fonts/cormorant-garamond-400-latin.woff2', weight: '400', unicodeRange: LATIN_RANGE },
  { family: 'Cormorant Garamond', file: 'fonts/cormorant-garamond-400-latin-ext.woff2', weight: '400', unicodeRange: LATIN_EXT_RANGE },
] as const

/** The seven distinct files the public dir must hold (JetBrains Mono's latin-ext file serves both weights). */
export const FONT_FILES: readonly string[] = [...new Set(FONTS.map((f) => f.file))]

export const HEADING = "'Orbitron', 'JetBrains Mono', sans-serif"
export const BODY = "'JetBrains Mono', monospace"
/** Verbatim passages of old texts (QuoteCard), the site's serif. */
export const SERIF = "'Cormorant Garamond', serif"

/** The loading started by loadBrandFonts(): resolves once every face is in document.fonts. */
let brandFonts: Promise<void> | null = null

export function loadBrandFonts(): void {
  brandFonts = Promise.all(
    FONTS.map((font) => loadFont({ family: font.family, url: staticFile(font.file), weight: font.weight, unicodeRange: font.unicodeRange })),
  ).then(() => undefined)
}

/**
 * Resolves once every brand face is in document.fonts. Until then text is laid
 * out in a fallback font with other metrics, so the lint-mode LayoutProvider
 * measures nothing before it. A file that fails to load has already cancelled
 * the render (loadFont calls cancelRender).
 */
export function brandFontsReady(): Promise<void> {
  if (!brandFonts) throw new Error('the brand fonts were never requested: src/Root.tsx calls loadBrandFonts() when it loads')
  return brandFonts
}
```

**`video/src/theme/glyphs.ts`** (complete file):

```ts
/**
 * The code points the brand fonts draw. LATIN_RANGE and LATIN_EXT_RANGE are the
 * unicode-range of the latin and latin-ext files fonts.ts loads, copied from
 * ancient-nerds-map/public/fonts/fonts.css. They decide which face Chrome tries for a
 * character, not whether that face has it: Google's subset files leave gaps in their
 * declared range (JetBrains Mono latin-ext has no Ḫ, Ḥ, Ṣ or Ṭ, its latin file no U+2011
 * or ‰), and Chrome draws such a character in a Windows system font without an error.
 *
 * DRAWABLE is therefore generated from the files themselves (scripts/fontCoverage.ts):
 * each loaded face's cmap within its unicode-range, the part common to the three stacks
 * of type.ts (heading, body/hud, serif), plus tab, line feed and carriage return, which
 * CSS lays out as white space. test/glyphs.test.ts recomputes it and fails on drift;
 * `npx tsx scripts/glyphs.ts` prints the new constant. blocks/index.ts checkBlocks refuses
 * every drawn timeline string with a character outside it, naming the scene, the prop
 * path and the character. heading() and hud() draw upper case (text-transform), which the
 * browser applies with the full Unicode mapping, so a character is drawable only when its
 * upper case is covered too ("ƒ" U+0192 turns into "Ƒ" U+0191, which no brand face maps).
 */
export const LATIN_RANGE =
  'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD'
export const LATIN_EXT_RANGE =
  'U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF'
export const DRAWABLE =
  'U+0009-000A, U+000D, U+0020-007E, U+00A0-00B4, U+00B6-0131, U+0134-017F, U+018F, U+0192, U+01A0-01A1, U+01AF-01B0, U+01CD-01CE, U+01E6-01E7, U+01EA-01EB, U+01FC-01FF, U+0218-021B, U+0232-0233, U+0237, U+0259, U+02BC, U+02C6-02C7, U+02DA, U+02DC-02DD, U+0304, U+0308, U+1E80-1E85, U+1E9E, U+1EF2-1EF9, U+2013-2014, U+2018-201A, U+201C-201E, U+2020, U+2022, U+2026, U+2032-2033, U+2039-203A, U+2044, U+20AB-20AC, U+20AE, U+20BD, U+2113, U+2122, U+2191, U+2193, U+2212, U+FEFF'

/** A CSS unicode-range ("U+0000-00FF, U+0131") as inclusive [first, last] code point pairs. */
export function parseUnicodeRange(css: string): [number, number][] {
  return css.split(',').map((part) => {
    const m = /^U\+([0-9A-F]+)(?:-([0-9A-F]+))?$/i.exec(part.trim())
    if (!m) throw new Error(`not a unicode-range entry: "${part.trim()}"`)
    const first = parseInt(m[1], 16)
    return [first, m[2] === undefined ? first : parseInt(m[2], 16)]
  })
}

const COVERED = parseUnicodeRange(DRAWABLE)

/** Whether the brand fonts draw every code point of `text` as written. */
function covered(text: string): boolean {
  return [...text].every((ch) => {
    const cp = ch.codePointAt(0) as number
    return COVERED.some(([first, last]) => cp >= first && cp <= last)
  })
}

/**
 * The first character of `text` the brand fonts cannot draw, as written or in upper
 * case (every code point of its full upper-case mapping), or null when they draw all of it.
 */
export function unsupportedChar(text: string): string | null {
  for (const ch of text) {
    if (!covered(ch) || !covered(ch.toUpperCase())) return ch
  }
  return null
}

const codes = (text: string) => [...text].map((ch) => `U+${(ch.codePointAt(0) as number).toString(16).toUpperCase().padStart(4, '0')}`).join(' ')

/** Why the brand fonts cannot draw `ch` (a character unsupportedChar returned): the written character or its upper case. */
export function glyphReason(ch: string): string {
  const upper = ch.toUpperCase()
  const turns = covered(ch) ? ` draws as "${upper}" (${codes(upper)}) in upper case, which` : ''
  return `"${ch}" (${codes(ch)})${turns} has no glyph in the brand fonts (latin and latin-ext only)`
}
```

**`video/scripts/fontCoverage.ts`** (complete file):

```ts
/**
 * Which code points the brand fonts really draw. Google's subset files do not cover
 * their whole declared unicode-range: JetBrains Mono latin-ext maps no Ḫ, Ḥ, Ṣ or Ṭ,
 * its latin file no U+2011 or ‰. Chrome draws a character the matching face lacks in the
 * next family of the stack and at last in a Windows system font, without an error. So
 * src/theme/glyphs.ts DRAWABLE comes from the woff2 files fonts.ts loads (each file's
 * cmap, read with Node's own brotli), never from their unicode-range alone:
 * test/glyphs.test.ts recomputes it and fails on drift, `npx tsx scripts/glyphs.ts`
 * (cwd video/) prints the constant.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { brotliDecompressSync } from 'node:zlib'

import { BODY, FONTS, HEADING, SERIF } from '../src/theme/fonts'
import { parseUnicodeRange } from '../src/theme/glyphs'

/** The site's public dir: `npm run studio` serves it, plan C's render step links its fonts/*.woff2. */
export const SITE_PUBLIC_DIR = fileURLToPath(new URL('../../ancient-nerds-map/public/', import.meta.url))

/** Tab, line feed and carriage return: CSS lays them out as white space or a line break, never as a glyph. */
const LAYOUT_WHITESPACE = [0x09, 0x0a, 0x0d]

// Indices in the WOFF2 known-table-tag list (WOFF2 spec 5.1); 63 means a four-byte tag follows.
const KNOWN_CMAP = 0
const KNOWN_GLYF = 10
const KNOWN_LOCA = 11
const ARBITRARY_TAG = 63

/** A WOFF2 UIntBase128 at `at.pos` (WOFF2 spec 4.1), advancing `at.pos`. */
function uintBase128(data: Buffer, at: { pos: number }): number {
  let value = 0
  for (let i = 0; i < 5; i++) {
    const byte = data[at.pos++]
    if (i === 0 && byte === 0x80) throw new Error('WOFF2 UIntBase128 with a leading zero byte')
    if (value > 0x1ffffff) throw new Error('WOFF2 UIntBase128 exceeds 32 bits')
    value = value * 128 + (byte & 0x7f)
    if ((byte & 0x80) === 0) return value
  }
  throw new Error('WOFF2 UIntBase128 longer than five bytes')
}

/**
 * The cmap table of a WOFF2 file: the table directory lists every table with its length,
 * then one brotli stream holds the tables in directory order without padding (WOFF2 spec 5).
 * glyf and loca are transformed unless their version is 3, any other table when its version
 * is not 0; cmap never is.
 */
function woff2CmapTable(path: string): Buffer {
  const file = readFileSync(path)
  if (file.toString('latin1', 0, 4) !== 'wOF2') throw new Error(`${path}: not a WOFF2 file`)
  if (file.toString('latin1', 4, 8) === 'ttcf') throw new Error(`${path}: a font collection, not a single font`)
  const numTables = file.readUInt16BE(12)
  const compressedLength = file.readUInt32BE(20)
  const at = { pos: 48 }
  let offset = 0
  let cmap: { offset: number; length: number } | undefined
  for (let i = 0; i < numTables; i++) {
    const flags = file[at.pos++]
    const known = flags & 0x3f
    const version = flags >> 6
    let tag = ''
    if (known === ARBITRARY_TAG) {
      tag = file.toString('latin1', at.pos, at.pos + 4)
      at.pos += 4
    }
    const origLength = uintBase128(file, at)
    const glyfOrLoca = known === KNOWN_GLYF || known === KNOWN_LOCA || tag === 'glyf' || tag === 'loca'
    const transformed = glyfOrLoca ? version !== 3 : version !== 0
    const length = transformed ? uintBase128(file, at) : origLength
    if (known === KNOWN_CMAP || tag === 'cmap') {
      if (transformed) throw new Error(`${path}: a transformed cmap table (version ${version})`)
      cmap = { offset, length }
    }
    offset += length
  }
  if (cmap === undefined) throw new Error(`${path}: no cmap table`)
  const tables = brotliDecompressSync(file.subarray(at.pos, at.pos + compressedLength))
  return tables.subarray(cmap.offset, cmap.offset + cmap.length)
}

/** Unicode cmap subtables (platform/encoding) in the order fontTools' getBestCmap prefers them. */
const UNICODE_SUBTABLES = ['3/10', '0/4', '3/1', '0/3']

/** Every code point a woff2 font file maps to a glyph other than .notdef (cmap formats 4 and 12). */
export function woff2Cmap(path: string): Set<number> {
  const cmap = woff2CmapTable(path)
  const records = new Map<string, number>()
  for (let i = 0; i < cmap.readUInt16BE(2); i++) {
    const rec = 4 + i * 8
    records.set(`${cmap.readUInt16BE(rec)}/${cmap.readUInt16BE(rec + 2)}`, cmap.readUInt32BE(rec + 4))
  }
  const key = UNICODE_SUBTABLES.find((k) => records.has(k))
  if (key === undefined) throw new Error(`${path}: no Unicode cmap subtable (${[...records.keys()].join(', ')})`)
  const at = records.get(key) as number
  const format = cmap.readUInt16BE(at)
  const points = new Set<number>()
  if (format === 4) {
    const segX2 = cmap.readUInt16BE(at + 6)
    const ends = at + 14
    const starts = ends + segX2 + 2
    const deltas = starts + segX2
    const rangeOffsets = deltas + segX2
    for (let s = 0; s < segX2; s += 2) {
      const start = cmap.readUInt16BE(starts + s)
      const end = cmap.readUInt16BE(ends + s)
      const delta = cmap.readUInt16BE(deltas + s)
      const rangeOffset = cmap.readUInt16BE(rangeOffsets + s)
      // U+FFFF only closes the segment list, it is never a character of the font
      for (let c = start; c <= end && c !== 0xffff; c++) {
        const indexed = rangeOffset === 0 ? c : cmap.readUInt16BE(rangeOffsets + s + rangeOffset + 2 * (c - start))
        const glyph = rangeOffset !== 0 && indexed === 0 ? 0 : (indexed + delta) & 0xffff
        if (glyph !== 0) points.add(c)
      }
    }
  } else if (format === 12) {
    const groups = cmap.readUInt32BE(at + 12)
    for (let g = 0; g < groups; g++) {
      const rec = at + 16 + g * 12
      const start = cmap.readUInt32BE(rec)
      const startGlyph = cmap.readUInt32BE(rec + 8)
      for (let c = start; c <= cmap.readUInt32BE(rec + 4); c++) if (startGlyph + c - start !== 0) points.add(c)
    }
  } else {
    throw new Error(`${path}: cmap subtable ${key} has format ${format}, only formats 4 and 12 are read`)
  }
  return points
}

function intersect(sets: Set<number>[]): Set<number> {
  const [first, ...rest] = sets
  return new Set([...first].filter((cp) => rest.every((set) => set.has(cp))))
}

/** The families a CSS font stack names, in order; the generic family at its end is the system font the glyph rule keeps text out of. */
function stackFamilies(stack: string): string[] {
  return stack
    .split(',')
    .map((family) => family.trim())
    .filter((family) => family.startsWith("'"))
    .map((family) => family.slice(1, -1))
}

/**
 * What one family draws at every weight fonts.ts loads for it: per weight, the union of its
 * faces' cmaps, each limited to the face's unicode-range (Chrome tries a face only for a
 * character inside its range); across weights, the common part.
 */
function familyCodePoints(family: string): Set<number> {
  const faces = FONTS.filter((face) => face.family === family)
  if (faces.length === 0) throw new Error(`fonts.ts FONTS loads no face of '${family}'`)
  const weights = [...new Set(faces.map((face) => face.weight))]
  return intersect(
    weights.map((weight) => {
      const points = new Set<number>()
      for (const face of faces.filter((f) => f.weight === weight)) {
        const ranges = parseUnicodeRange(face.unicodeRange)
        for (const cp of woff2Cmap(join(SITE_PUBLIC_DIR, face.file))) {
          if (ranges.some(([first, last]) => cp >= first && cp <= last)) points.add(cp)
        }
      }
      return points
    }),
  )
}

/**
 * The code points every stack of type.ts (HEADING for heading(), BODY for body() and hud(),
 * SERIF for serif()) draws with a loaded brand face, plus the layout white space.
 */
export function drawableCodePoints(): Set<number> {
  const stacks = [HEADING, BODY, SERIF].map((stack) => {
    const points = new Set<number>()
    for (const family of stackFamilies(stack)) for (const cp of familyCodePoints(family)) points.add(cp)
    return points
  })
  return new Set([...intersect(stacks), ...LAYOUT_WHITESPACE])
}

const hex = (cp: number) => cp.toString(16).toUpperCase().padStart(4, '0')

/** Code points as a CSS unicode-range ("U+0020-007E, U+00A0"), ascending, consecutive ones merged. */
export function formatUnicodeRange(points: Iterable<number>): string {
  const runs: [number, number][] = []
  for (const cp of [...new Set(points)].sort((a, b) => a - b)) {
    const last = runs[runs.length - 1]
    if (last !== undefined && last[1] === cp - 1) last[1] = cp
    else runs.push([cp, cp])
  }
  return runs.map(([first, last]) => (first === last ? `U+${hex(first)}` : `U+${hex(first)}-${hex(last)}`)).join(', ')
}

/** DRAWABLE of src/theme/glyphs.ts as the brand font files define it today. */
export const drawableRange = (): string => formatUnicodeRange(drawableCodePoints())
```

**`video/scripts/glyphs.ts`** (complete file):

```ts
/**
 * Prints src/theme/glyphs.ts DRAWABLE recomputed from the brand font files
 * (scripts/fontCoverage.ts): `npx tsx scripts/glyphs.ts`, cwd video/. Paste the
 * output over the constant when test/glyphs.test.ts reports drift.
 */
import { drawableRange } from './fontCoverage'

console.log(`export const DRAWABLE =\n  '${drawableRange()}'`)
```

**`video/src/theme/type.ts`** (complete file):

```ts
/** Text styles shared by every block (sizes in composition pixels at 1920x1080). */
import type { CSSProperties } from 'react'

import { colors } from './colors'
import { BODY, HEADING, SERIF } from './fonts'

export const heading = (size: number, color: string = colors.white): CSSProperties => ({
  fontFamily: HEADING,
  fontWeight: 700,
  fontSize: size,
  lineHeight: 1.15,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color,
})

export const body = (size: number, color: string = colors.text): CSSProperties => ({
  fontFamily: BODY,
  fontWeight: 400,
  fontSize: size,
  lineHeight: 1.35,
  color,
})

export const hud = (size: number, color: string = colors.green): CSSProperties => ({
  fontFamily: BODY,
  fontWeight: 500,
  fontSize: size,
  lineHeight: 1.2,
  letterSpacing: '0.14em',
  textTransform: 'uppercase',
  color,
})

export const serif = (size: number, color: string = colors.white): CSSProperties => ({
  fontFamily: SERIF,
  fontWeight: 400,
  fontSize: size,
  lineHeight: 1.25,
  color,
})

/** Readable over footage: a soft dark halo instead of a box. */
export const overFootage: CSSProperties = { textShadow: '0 2px 10px rgba(0, 0, 0, 0.95), 0 0 2px rgba(0, 0, 0, 0.9)' }
```

**`video/src/motion/index.ts`** (complete file):

```ts
/**
 * Frame-driven NERV motion: the renderer's port of
 * ancient-nerds-map/src/styles/nerv-animations.css. Every value is a pure
 * function of the frame (Remotion renders frames out of order in parallel
 * tabs, so CSS animations or transitions would freeze or flicker). Durations
 * are frames at the timeline's 60 fps (crt-open 0.4 s = 24, boot-in 0.5 s = 30).
 *
 * Deliberately absent (owner rule: no flicker): flicker, flicker-in,
 * glitch-tear, alert-flash, emergency-flash, warning-flash, led-blink and
 * blink-cursor. Periodic motion (ringPulse) fades smoothly, it never blinks.
 */
import type { CSSProperties } from 'react'
import { Easing, interpolate, spring } from 'remotion'

const CLAMP = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const

/** 0 before `start`, 1 from `start + duration` on, eased in between. */
export function progress(frame: number, start: number, duration: number, easing: (t: number) => number = Easing.out(Easing.cubic)): number {
  if (duration <= 0) return frame >= start ? 1 : 0
  return interpolate(frame, [start, start + duration], [0, 1], { ...CLAMP, easing })
}

/** crt-open: the panel opens from a bright horizontal line (scaleY .002 until 40 %, brightness 3 -> 1). */
export function crtOpen(frame: number, start = 0, duration = 24): CSSProperties {
  if (frame < start) return { opacity: 0 }
  const p = progress(frame, start, duration, Easing.linear)
  const scaleY = interpolate(p, [0, 0.4, 1], [0.002, 0.002, 1], CLAMP)
  const brightness = interpolate(p, [0, 0.4, 1], [3, 2, 1], CLAMP)
  return { opacity: 1, transform: `scaleY(${scaleY})`, filter: `brightness(${brightness})` }
}

/** boot-in: rises 8 px, fades in and settles from a brightness flash. `base` is prepended to the transform. */
export function bootIn(frame: number, start = 0, duration = 30, base = ''): CSSProperties {
  const p = progress(frame, start, duration)
  const brightness = interpolate(p, [0, 0.4, 1], [2, 1.5, 1], CLAMP)
  return {
    opacity: p,
    transform: `${base ? `${base} ` : ''}translateY(${(1 - p) * 8}px)`,
    filter: `brightness(${brightness})`,
  }
}

/** border-trace: stroke-dashoffset of an SVG outline of `perimeter` length. */
export function borderTrace(frame: number, start: number, duration: number, perimeter: number): number {
  return perimeter * (1 - progress(frame, start, duration, Easing.inOut(Easing.quad)))
}

/** type-on: the visible prefix of `text`, `charsPerFrame` characters per frame from `start`. */
export function typeOn(text: string, frame: number, start: number, charsPerFrame = 1.5): string {
  if (frame < start) return ''
  const n = Math.min(text.length, Math.floor((frame - start + 1) * charsPerFrame))
  return text.slice(0, n)
}

/** digit-roll: a number counting from `from` to `to`, rounded to `decimals`. */
export function digitRoll(from: number, to: number, frame: number, start: number, duration = 36, decimals = 0): number {
  const v = from + (to - from) * progress(frame, start, duration)
  const f = 10 ** decimals
  return Math.round(v * f) / f
}

/**
 * Stamp slam: drops in from 1.35x with a spring, tilted -6 degrees. The start
 * scale stays small enough that a stamp never covers its neighbours on its
 * first frames (the lint pass measures the transformed stamp).
 */
export function stampSlam(frame: number, start: number, fps: number): CSSProperties {
  if (frame < start) return { opacity: 0 }
  const s = spring({ frame: frame - start, fps, config: { damping: 11, stiffness: 190, mass: 0.7 } })
  const scale = interpolate(s, [0, 1], [1.35, 1])
  return { opacity: Math.min(1, (frame - start + 1) / 3), transform: `rotate(-6deg) scale(${scale})` }
}

/** ring-pulse: a ring expanding from 0.8x to 1.6x and fading from 0.6 to 0, every `period` frames. */
export function ringPulse(frame: number, start: number, period = 60): { scale: number; opacity: number } {
  if (frame < start) return { scale: 0.8, opacity: 0 }
  const phase = ((frame - start) % period) / period
  return { scale: 0.8 + phase * 0.8, opacity: 0.6 * (1 - phase) }
}

/** sweep: 0..1 position of a light wipe crossing once. */
export function sweep(frame: number, start: number, duration: number): number {
  return progress(frame, start, duration, Easing.inOut(Easing.sin))
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/motion.test.ts test/colors.test.ts test/glyphs.test.ts`
Expected: `Tests  29 passed (29)` (9 motion, 14 palette mirror, 6 glyphs). Then `npx tsx scripts/glyphs.ts` prints exactly the `DRAWABLE` constant of `glyphs.ts`.

- [ ] **Step 5: Commit**

```bash
git add video/src/theme/colors.ts video/src/theme/fonts.ts video/src/theme/glyphs.ts video/src/theme/type.ts video/src/motion/index.ts video/scripts/fontCoverage.ts video/scripts/glyphs.ts video/test/motion.test.ts video/test/colors.test.ts video/test/glyphs.test.ts
git commit -m "Add the renderer's NERV palette mirrored from the site, brand fonts with latin-ext, and frame-driven motion without flicker" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: The JSON-schema subset of the block registry

**Files:**
- Create: `video/src/schema.ts`
- Test: `video/test/schema.test.ts`

Plan C's `pipeline/studio/blocks.py` validates script props against `registry.json` with its own implementation of exactly this keyword subset (contract C5); the renderer validates scene props with this one.

- [ ] **Step 1: Write the failing test**

**`video/test/schema.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { type Schema, unsupportedKeywords, validate } from '../src/schema'

const schema: Schema = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'n'],
  properties: {
    id: { type: 'string', minLength: 1, maxLength: 4 },
    n: { type: 'integer', minimum: 1, maximum: 9 },
    tone: { type: 'string', enum: ['accent', 'warn'] },
    box: { type: 'array', minItems: 4, maxItems: 4, items: { type: 'number' } },
    anchor: { type: ['string', 'null'] },
    extra: { type: 'object', additionalProperties: { type: 'number' } },
  },
}

describe('validate', () => {
  it('accepts a valid object (integers count as numbers, null where listed)', () => {
    expect(validate(schema, { id: 'c1', n: 3, tone: 'warn', box: [1, 2.5, 3, 4], anchor: null, extra: { a: 1 } })).toEqual([])
  })
  it('reports each defect with its path', () => {
    expect(validate(schema, { id: 'toolong', n: 12, tone: 'red', box: [1, 2], other: true })).toEqual([
      '$.id: longer than 4',
      '$.n: 12 is above 9',
      '$.tone: "red" is not one of ["accent","warn"]',
      '$.box: fewer than 4 items',
      '$.other: not allowed',
    ])
    expect(validate(schema, { id: 'a' })).toEqual(['$.n: missing'])
    expect(validate(schema, { id: 'a', n: 1.5 })).toEqual(['$.n: expected integer, got number'])
    expect(validate(schema, { id: 'a', n: 1, extra: { a: 'x' } })).toEqual(['$.extra.a: expected number, got string'])
  })
  it('finds keywords outside the subset pipeline/studio/blocks.py accepts', () => {
    expect(unsupportedKeywords({ type: 'object', properties: { a: { oneOf: [] } as unknown as Schema } })).toEqual(['$.properties.a.oneOf'])
    expect(unsupportedKeywords({ type: 'string', pattern: '^x$' } as unknown as Schema)).toEqual(['$.pattern'])
    expect(unsupportedKeywords({ type: 'array', items: { type: 'number', $comment: 'fine', title: 't', default: 1 } })).toEqual([])
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/schema.test.ts`
Expected: FAIL with `Cannot find module '../src/schema'`.

- [ ] **Step 3: Implement**

**`video/src/schema.ts`** (complete file):

```ts
/**
 * The JSON-Schema subset of the block registry (plan C contract C5). The
 * renderer validates scene props with it; pipeline/studio/blocks.py validates
 * script props against the same registry.json with its own implementation of
 * the same subset, and refuses any other keyword at load. test/schema.test.ts
 * and test/registry.test.ts keep every block schema inside SUPPORTED.
 */
export type SchemaType = 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array' | 'null'

export type Schema = {
  type?: SchemaType | SchemaType[]
  properties?: Record<string, Schema>
  required?: string[]
  additionalProperties?: boolean | Schema
  items?: Schema
  enum?: readonly (string | number | boolean | null)[]
  minimum?: number
  maximum?: number
  minItems?: number
  maxItems?: number
  minLength?: number
  maxLength?: number
  description?: string
  title?: string
  default?: unknown
  $comment?: string
}

export const SUPPORTED: ReadonlySet<string> = new Set([
  'type',
  'properties',
  'required',
  'additionalProperties',
  'items',
  'enum',
  'minimum',
  'maximum',
  'minItems',
  'maxItems',
  'minLength',
  'maxLength',
  'description',
  'title',
  'default',
  '$comment',
])

function typeOf(v: unknown): SchemaType {
  if (v === null) return 'null'
  if (Array.isArray(v)) return 'array'
  if (typeof v === 'number') return Number.isInteger(v) ? 'integer' : 'number'
  if (typeof v === 'string' || typeof v === 'boolean' || typeof v === 'object') return typeof v as SchemaType
  throw new Error(`unsupported JSON value of type ${typeof v}`)
}

function typeMatches(actual: SchemaType, wanted: SchemaType): boolean {
  return actual === wanted || (wanted === 'number' && actual === 'integer')
}

/** Errors as "<path>: <message>"; an empty list means valid. */
export function validate(schema: Schema, value: unknown, path = '$'): string[] {
  const errors: string[] = []
  const actual = typeOf(value)
  if (schema.type !== undefined) {
    const wanted = Array.isArray(schema.type) ? schema.type : [schema.type]
    if (!wanted.some((w) => typeMatches(actual, w))) return [`${path}: expected ${wanted.join('|')}, got ${actual}`]
  }
  if (schema.enum !== undefined && !schema.enum.includes(value as string | number | boolean | null)) {
    errors.push(`${path}: ${JSON.stringify(value)} is not one of ${JSON.stringify(schema.enum)}`)
  }
  if (typeof value === 'number') {
    if (schema.minimum !== undefined && value < schema.minimum) errors.push(`${path}: ${value} is below ${schema.minimum}`)
    if (schema.maximum !== undefined && value > schema.maximum) errors.push(`${path}: ${value} is above ${schema.maximum}`)
  }
  if (typeof value === 'string') {
    if (schema.minLength !== undefined && value.length < schema.minLength) errors.push(`${path}: shorter than ${schema.minLength}`)
    if (schema.maxLength !== undefined && value.length > schema.maxLength) errors.push(`${path}: longer than ${schema.maxLength}`)
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push(`${path}: fewer than ${schema.minItems} items`)
    if (schema.maxItems !== undefined && value.length > schema.maxItems) errors.push(`${path}: more than ${schema.maxItems} items`)
    if (schema.items) {
      const items = schema.items
      value.forEach((item, i) => errors.push(...validate(items, item, `${path}[${i}]`)))
    }
  }
  if (actual === 'object') {
    const obj = value as Record<string, unknown>
    for (const key of schema.required ?? []) {
      if (!(key in obj)) errors.push(`${path}.${key}: missing`)
    }
    for (const [key, v] of Object.entries(obj)) {
      const sub = schema.properties?.[key]
      if (sub) errors.push(...validate(sub, v, `${path}.${key}`))
      else if (schema.additionalProperties === false) errors.push(`${path}.${key}: not allowed`)
      else if (typeof schema.additionalProperties === 'object') errors.push(...validate(schema.additionalProperties, v, `${path}.${key}`))
    }
  }
  return errors
}

/** Keywords used anywhere in `schema` outside SUPPORTED, as JSON paths. */
export function unsupportedKeywords(schema: Schema, path = '$'): string[] {
  const out: string[] = []
  for (const key of Object.keys(schema)) {
    if (!SUPPORTED.has(key)) out.push(`${path}.${key}`)
  }
  for (const [name, sub] of Object.entries(schema.properties ?? {})) out.push(...unsupportedKeywords(sub, `${path}.properties.${name}`))
  if (typeof schema.additionalProperties === 'object') out.push(...unsupportedKeywords(schema.additionalProperties, `${path}.additionalProperties`))
  if (schema.items) out.push(...unsupportedKeywords(schema.items, `${path}.items`))
  return out
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/schema.test.ts`
Expected: `Tests  3 passed (3)`

- [ ] **Step 5: Commit**

```bash
git add video/src/schema.ts video/test/schema.test.ts
git commit -m "Validate block props with the registry's JSON-schema subset" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: Screen zones and the pure overlap checker

**Files:**
- Create: `video/src/layout/zones.ts`, `video/src/layout/geometry.ts`
- Test: `video/test/geometry.test.ts`

The 1920x1080 frame has fixed zones (chapter tag and ticker on top, the stage, hook captions, lower third and credit line, and the bottom 120 px the YouTube player covers). `findViolations` is the lint's judge: readable text stays inside the title-safe area and out of the player controls, text never covers other text or a marker unless one allows the other (a marker's own label), a marker is fully on screen and out of the player controls too (owner rule: nothing important in YouTube's control zone), and a clipped text box is an overflow.

- [ ] **Step 1: Write the failing test**

**`video/test/geometry.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { type Box, contains, findViolations, overlapArea } from '../src/layout/geometry'
import { SAFE, ZONES, stageFor } from '../src/layout/zones'

const text = (id: string, x: number, y: number, w: number, h: number, allow: string[] = []): Box => ({ id, kind: 'text', rect: { x, y, w, h }, allow })
const mark = (id: string, x: number, y: number, w: number, h: number, allow: string[] = []): Box => ({ id, kind: 'mark', rect: { x, y, w, h }, allow })

describe('overlapArea / contains', () => {
  it('measures the shared area and ignores touching edges', () => {
    expect(overlapArea({ x: 0, y: 0, w: 10, h: 10 }, { x: 5, y: 5, w: 10, h: 10 })).toBe(25)
    expect(overlapArea({ x: 0, y: 0, w: 10, h: 10 }, { x: 10, y: 0, w: 10, h: 10 })).toBe(0)
  })
  it('contains with half a pixel of tolerance', () => {
    expect(contains(SAFE, { x: 95.6, y: 54, w: 10, h: 10 })).toBe(true)
    expect(contains(SAFE, { x: 90, y: 54, w: 10, h: 10 })).toBe(false)
  })
})

describe('zones', () => {
  it('keeps every overlay zone apart and inside the safe area', () => {
    const boxes = Object.entries(ZONES)
      .filter(([name]) => name !== 'stage' && name !== 'stageHook')
      .map(([name, z]) => text(name, z.x, z.y, z.w, z.h))
    expect(findViolations(boxes)).toEqual([])
  })
  it('keeps the hook stage above the captions', () => {
    const s = stageFor(true)
    expect(s.y + s.h).toBeLessThanOrEqual(ZONES.caption.y)
    expect(stageFor(false)).toEqual(ZONES.stage)
  })
})

describe('findViolations', () => {
  it('reports two overlapping text boxes once, with both ids', () => {
    expect(findViolations([text('a', 200, 200, 300, 60), text('b', 400, 220, 300, 60)])).toEqual([{ a: 'a', b: 'b', reason: 'overlap' }])
  })
  it('lets a marker label touch its own ring but not a foreign ring', () => {
    const ring = mark('ring1', 500, 500, 100, 100, ['label1'])
    expect(findViolations([ring, text('label1', 520, 560, 200, 40, ['ring1'])])).toEqual([])
    expect(findViolations([ring, text('label2', 520, 560, 200, 40)])).toEqual([{ a: 'ring1', b: 'label2', reason: 'overlap' }])
  })
  it('flags text outside the safe area and text under the player controls', () => {
    expect(findViolations([text('edge', 20, 300, 200, 40)])).toEqual([{ a: 'edge', b: null, reason: 'outside-safe' }])
    expect(findViolations([text('low', 300, 950, 200, 40)])).toEqual([{ a: 'low', b: null, reason: 'controls' }])
  })
  it('flags a marker that leaves the frame, never two markers touching', () => {
    expect(findViolations([mark('m', 1880, 500, 80, 80)])).toEqual([{ a: 'm', b: null, reason: 'offscreen' }])
    expect(findViolations([mark('m1', 500, 500, 80, 80), mark('m2', 520, 520, 80, 80)])).toEqual([])
  })
  it('flags a marker under the player controls (nothing important in the control zone)', () => {
    expect(findViolations([mark('m', 500, 980, 60, 60)])).toEqual([{ a: 'm', b: null, reason: 'controls' }])
  })
  it('reports clipped text boxes as overflow', () => {
    expect(findViolations([], ['b03:statement'])).toEqual([{ a: 'b03:statement', b: null, reason: 'overflow' }])
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/geometry.test.ts`
Expected: FAIL with `Cannot find module '../src/layout/geometry'`.

- [ ] **Step 3: Implement**

**`video/src/layout/zones.ts`** (complete file):

```ts
/**
 * Screen zones of the 1920x1080 episode frame. Overlays sit in fixed zones so
 * they cannot collide by construction; the lint pass (LayoutGuard) proves it
 * frame by frame.
 *
 *   chapter tag (top left) ........................ ticker (top right)   y 60..124
 *   stage: block content ...............................................  y 140..820
 *     (stageHook: y 140..680 in scenes with burned-in hook captions)
 *   hook captions (hook beats only) ....................................  y 700..820
 *   lower third (left) ......................... credit line (right)     y 846..954
 *   YouTube player controls: no text ...................................  y 960..1080
 */
import type { Rect } from './geometry'

export const FRAME: Rect = { x: 0, y: 0, w: 1920, h: 1080 }
/** 5 % title-safe inset. */
export const SAFE: Rect = { x: 96, y: 54, w: 1728, h: 972 }
/** Scrub bar and buttons of the YouTube player (bottom 120 px at 1080p). */
export const YT_CONTROLS: Rect = { x: 0, y: 960, w: 1920, h: 120 }

export const ZONES = {
  chapter: { x: 96, y: 60, w: 720, h: 48 },
  ticker: { x: 1464, y: 60, w: 360, h: 64 },
  stage: { x: 96, y: 140, w: 1728, h: 680 },
  stageHook: { x: 96, y: 140, w: 1728, h: 540 },
  caption: { x: 240, y: 700, w: 1440, h: 120 },
  lowerThird: { x: 96, y: 846, w: 760, h: 96 },
  credit: { x: 1024, y: 922, w: 800, h: 32 },
} as const satisfies Record<string, Rect>

/** The stage a scene's block may fill: shorter when the scene carries hook captions. */
export function stageFor(captioned: boolean): Rect {
  return captioned ? ZONES.stageHook : ZONES.stage
}
```

**`video/src/layout/geometry.ts`** (complete file):

```ts
/**
 * Pure rectangle geometry and the overlap checker behind the lint pass.
 * Boxes are in composition pixels (1920x1080), measured by LayoutBox.
 */
import { FRAME, SAFE, YT_CONTROLS } from './zones'

export type Rect = { x: number; y: number; w: number; h: number }

/** text: readable copy (captions, labels, card text); mark: a marker or pin drawn on an object. */
export type BoxKind = 'text' | 'mark'

export type Box = { id: string; kind: BoxKind; rect: Rect; allow: string[] }

export type ViolationReason = 'overlap' | 'outside-safe' | 'controls' | 'offscreen' | 'overflow'

export type Violation = { a: string; b: string | null; reason: ViolationReason }

/** Overlaps smaller than this (square px) are anti-aliasing contact, not a collision. */
const MIN_OVERLAP_AREA = 4

export function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

export function contains(outer: Rect, inner: Rect): boolean {
  const eps = 0.5
  return (
    inner.x >= outer.x - eps &&
    inner.y >= outer.y - eps &&
    inner.x + inner.w <= outer.x + outer.w + eps &&
    inner.y + inner.h <= outer.y + outer.h + eps
  )
}

/**
 * Rules:
 * - text sits inside the title-safe area and never under the YouTube player controls;
 * - text does not cover other text or a marker, unless one of the two lists the other in
 *   `allow` (a marker's own label may touch its ring);
 * - a marker is fully on screen (a clipped ring points at nothing) and, like text, out of
 *   the YouTube player controls (owner rule: nothing important in the control zone);
 * - `overflowIds`: text boxes whose content is clipped by their own box (measured in the DOM).
 */
export function findViolations(boxes: readonly Box[], overflowIds: readonly string[] = []): Violation[] {
  const out: Violation[] = []
  for (const id of overflowIds) out.push({ a: id, b: null, reason: 'overflow' })
  for (const box of boxes) {
    if (box.kind === 'text') {
      if (!contains(SAFE, box.rect)) out.push({ a: box.id, b: null, reason: 'outside-safe' })
    } else if (!contains(FRAME, box.rect)) {
      out.push({ a: box.id, b: null, reason: 'offscreen' })
    }
    if (overlapArea(box.rect, YT_CONTROLS) >= MIN_OVERLAP_AREA) out.push({ a: box.id, b: null, reason: 'controls' })
  }
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i]
      const b = boxes[j]
      if (a.kind === 'mark' && b.kind === 'mark') continue
      if (a.allow.includes(b.id) || b.allow.includes(a.id)) continue
      if (overlapArea(a.rect, b.rect) >= MIN_OVERLAP_AREA) out.push({ a: a.id, b: b.id, reason: 'overlap' })
    }
  }
  return out
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/geometry.test.ts`
Expected: `Tests  10 passed (10)`

- [ ] **Step 5: Commit**

```bash
git add video/src/layout/zones.ts video/src/layout/geometry.ts video/test/geometry.test.ts
git commit -m "Define the episode's screen zones and the pure overlap checker behind the layout lint" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: Image-to-screen math: markers move with their image

**Files:**
- Create: `video/src/layout/transform.ts`
- Test: `video/test/transform.test.ts`

Owner rule: markers live in the same layer as their image and move with it. An image is cover-fitted and zoomed around a camera point; markers are drawn in image pixels inside the same transformed layer, and their labels are placed through the same `View`. The Ken Burns push is 8 %; a highlight flies the camera onto a marker so it fills 45 % of the frame.

- [ ] **Step 1: Write the failing test**

**`video/test/transform.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { cameraAt, coverScale, focusCamera, fractionBox, kenBurnsCamera, rectToScreen, toScreen, viewFor } from '../src/layout/transform'

describe('cover fit and camera view', () => {
  it('cover-fits a 4:3 image into 16:9 by width', () => {
    expect(coverScale(1600, 1200, 1920, 1080)).toBeCloseTo(1.2)
  })
  it('centres the camera point on screen when the image allows it', () => {
    const v = viewFor(4000, 3000, 1920, 1080, { cx: 2000, cy: 1500, zoom: 2 })
    const c = toScreen(v, 2000, 1500)
    expect(c.x).toBeCloseTo(960)
    expect(c.y).toBeCloseTo(540)
  })
  it('clamps at the image edge so no background ever shows', () => {
    const v = viewFor(1600, 1200, 1920, 1080, { cx: 0, cy: 0, zoom: 1 })
    expect(v.tx).toBe(0)
    expect(v.ty).toBe(0)
    const far = viewFor(1600, 1200, 1920, 1080, { cx: 1600, cy: 1200, zoom: 1 })
    expect(far.tx).toBeCloseTo(1920 - 1600 * far.scale)
    expect(far.ty).toBeCloseTo(1080 - 1200 * far.scale)
  })
})

describe('markers move with the image', () => {
  it('turns case-file fraction boxes into image pixels', () => {
    expect(fractionBox([0.1, 0.5, 0.1, 0.3], 1600, 1200)).toEqual([160, 600, 160, 360])
  })
  it('maps a marker box through the same view as the image pixels it covers', () => {
    const box = [1000, 700, 120, 240] as const
    for (const cam of [{ cx: 800, cy: 600, zoom: 1 }, { cx: 1060, cy: 820, zoom: 3 }]) {
      const v = viewFor(1600, 1200, 1920, 1080, cam)
      const r = rectToScreen(v, box)
      const tl = toScreen(v, box[0], box[1])
      const br = toScreen(v, box[0] + box[2], box[1] + box[3])
      expect(r.x).toBeCloseTo(tl.x)
      expect(r.y).toBeCloseTo(tl.y)
      expect(r.x + r.w).toBeCloseTo(br.x)
      expect(r.y + r.h).toBeCloseTo(br.y)
    }
  })
  it('keeps the focused marker centred and large', () => {
    const box = [1000, 700, 120, 240] as const
    const r = rectToScreen(viewFor(1600, 1200, 1920, 1080, focusCamera(1600, 1200, 1920, 1080, box)), box)
    expect(r.x + r.w / 2).toBeCloseTo(960, 0)
    expect(r.y + r.h / 2).toBeCloseTo(540, 0)
    expect(r.h / 1080).toBeCloseTo(0.45, 2)
  })
})

describe('camera paths', () => {
  it('holds the ends and eases between keys, zoom in log space', () => {
    const keys = [
      { at: 0, cx: 0, cy: 0, zoom: 1 },
      { at: 1, cx: 100, cy: 50, zoom: 4 },
    ]
    expect(cameraAt(keys, -1)).toEqual({ cx: 0, cy: 0, zoom: 1 })
    expect(cameraAt(keys, 2)).toEqual({ cx: 100, cy: 50, zoom: 4 })
    const mid = cameraAt(keys, 0.5)
    expect(mid.cx).toBeCloseTo(50)
    expect(mid.zoom).toBeCloseTo(2)
    expect(() => cameraAt([], 0.5)).toThrow(/no keyframes/)
  })
  it('pushes in, pulls out or holds still on the image centre', () => {
    expect(kenBurnsCamera(1000, 800, 'in')).toEqual([
      { at: 0, cx: 500, cy: 400, zoom: 1 },
      { at: 1, cx: 500, cy: 400, zoom: 1.08 },
    ])
    expect(kenBurnsCamera(1000, 800, 'out')[0].zoom).toBe(1.08)
    expect(kenBurnsCamera(1000, 800, 'none')).toEqual([{ at: 0, cx: 500, cy: 400, zoom: 1 }])
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/transform.test.ts`
Expected: FAIL with `Cannot find module '../src/layout/transform'`.

- [ ] **Step 3: Implement**

**`video/src/layout/transform.ts`** (complete file):

```ts
/**
 * Pure image-to-screen math for PhotoPlate, MapboxTopdown and PlatformClip.
 * An image (or captured video) of iw x ih pixels is fitted with "cover" into
 * the frame and zoomed around a camera centre. Markers are positioned in image
 * pixels inside the same transformed layer, so they move with the image
 * exactly; labels are placed in screen space through toScreen().
 */
import type { Rect } from './geometry'

export type Camera = { cx: number; cy: number; zoom: number }
export type CameraKey = Camera & { at: number }
export type ImageBox = readonly [number, number, number, number]
/** screen = image * scale + (tx, ty) */
export type View = { scale: number; tx: number; ty: number }

export function coverScale(iw: number, ih: number, fw: number, fh: number): number {
  return Math.max(fw / iw, fh / ih)
}

/** View that centres (cx, cy) at `zoom` times the cover scale, clamped so the image always fills the frame. */
export function viewFor(iw: number, ih: number, fw: number, fh: number, cam: Camera): View {
  const scale = coverScale(iw, ih, fw, fh) * Math.max(1, cam.zoom)
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
  const tx = clamp(fw / 2 - cam.cx * scale, fw - iw * scale, 0)
  const ty = clamp(fh / 2 - cam.cy * scale, fh - ih * scale, 0)
  return { scale, tx, ty }
}

export function toScreen(v: View, x: number, y: number): { x: number; y: number } {
  return { x: x * v.scale + v.tx, y: y * v.scale + v.ty }
}

export function rectToScreen(v: View, box: ImageBox): Rect {
  const p = toScreen(v, box[0], box[1])
  return { x: p.x, y: p.y, w: box[2] * v.scale, h: box[3] * v.scale }
}

/** A box given as fractions of the image ([x, y, w, h] in 0..1, the case file's marker boxes) in image pixels. */
export function fractionBox(box: readonly number[], iw: number, ih: number): ImageBox {
  return [box[0] * iw, box[1] * ih, box[2] * iw, box[3] * ih]
}

const smoothstep = (u: number) => u * u * (3 - 2 * u)

/** Blend two cameras (e = 0..1); zoom is interpolated in log space so it feels even. */
export function blendCamera(a: Camera, b: Camera, e: number): Camera {
  const lerp = (x: number, y: number) => x + (y - x) * e
  return { cx: lerp(a.cx, b.cx), cy: lerp(a.cy, b.cy), zoom: Math.exp(lerp(Math.log(a.zoom), Math.log(b.zoom))) }
}

/** Camera at fraction t (0..1) of the keyframes: smoothstep per segment. */
export function cameraAt(keys: readonly CameraKey[], t: number): Camera {
  if (keys.length === 0) throw new Error('cameraAt: no keyframes')
  const first = keys[0]
  const last = keys[keys.length - 1]
  if (keys.length === 1 || t <= first.at) return { cx: first.cx, cy: first.cy, zoom: first.zoom }
  if (t >= last.at) return { cx: last.cx, cy: last.cy, zoom: last.zoom }
  let i = 1
  while (keys[i].at < t) i++
  const a = keys[i - 1]
  const b = keys[i]
  return blendCamera(a, b, smoothstep((t - a.at) / Math.max(b.at - a.at, 1e-6)))
}

/** Camera that frames `box` so it fills `fill` of the frame on its tighter side (zoom 1..4). */
export function focusCamera(iw: number, ih: number, fw: number, fh: number, box: ImageBox, fill = 0.45): Camera {
  const base = coverScale(iw, ih, fw, fh)
  const zoom = Math.min(4, Math.max(1, Math.min((fw * fill) / (box[2] * base), (fh * fill) / (box[3] * base))))
  return { cx: box[0] + box[2] / 2, cy: box[1] + box[3] / 2, zoom }
}

export type KenBurns = 'in' | 'out' | 'none'

/** Ken Burns keyframes on the image centre: an 8 % push in, pull out, or a still frame. */
export function kenBurnsCamera(iw: number, ih: number, mode: KenBurns): CameraKey[] {
  const centre = { cx: iw / 2, cy: ih / 2 }
  if (mode === 'none') return [{ at: 0, ...centre, zoom: 1 }]
  const [from, to] = mode === 'in' ? [1, 1.08] : [1.08, 1]
  return [
    { at: 0, ...centre, zoom: from },
    { at: 1, ...centre, zoom: to },
  ]
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/transform.test.ts`
Expected: `Tests  8 passed (8)`

- [ ] **Step 5: Commit**

```bash
git add video/src/layout/transform.ts video/test/transform.test.ts
git commit -m "Add the camera and marker transform math so markers stay on their object while the image moves" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: Text formatting shared by the blocks

**Files:**
- Create: `video/src/format.ts`
- Test: `video/test/format.test.ts`

Distances on a top-down frame are computed from the pins' coordinates (haversine), never typed; years are BCE/CE without a year 0; the meter's words are the papers' house probability language.

- [ ] **Step 1: Write the failing test**

**`video/test/format.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { domainOf, formatDistance, formatNumber, formatYear, haversineM, verbal, yearTicks } from '../src/format'

describe('format', () => {
  it('shows the domain without www', () => {
    expect(domainOf('https://www.dainst.org/baalbek?x=1')).toBe('dainst.org')
    expect(domainOf('https://en.wikipedia.org/wiki/Baalbek')).toBe('en.wikipedia.org')
  })
  it('measures and formats distances from coordinates', () => {
    // Baalbek quarry to the Temple of Jupiter: about 850 m
    const d = haversineM({ lat: 33.99917, lng: 36.20028 }, { lat: 34.00667, lng: 36.20333 })
    expect(d).toBeGreaterThan(800)
    expect(d).toBeLessThan(900)
    expect(formatDistance(d)).toMatch(/^8[0-9]0 m$/)
    expect(formatDistance(1449)).toBe('1.4 km')
    expect(formatDistance(23_400)).toBe('23 km')
  })
  it('writes BCE/CE years and refuses year 0', () => {
    expect(formatYear(-3000)).toBe('3000 BCE')
    expect(formatYear(120)).toBe('120 CE')
    expect(() => formatYear(0)).toThrow(/year 0/)
    expect(yearTicks(-200, 300)).toEqual([-200, -100, 100, 200, 300])
  })
  it('uses the house probability words', () => {
    expect([95, 80, 65, 50, 30, 10].map(verbal)).toEqual(['almost certain', 'very likely', 'likely', 'roughly even', 'unlikely', 'very unlikely'])
  })
  it('groups thousands', () => {
    expect(formatNumber(1650)).toBe('1,650')
    expect(formatNumber(12.54)).toBe('12.5')
    expect(formatNumber(1.75, 2)).toBe('1.75')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/format.test.ts`
Expected: FAIL with `Cannot find module '../src/format'`.

- [ ] **Step 3: Implement**

**`video/src/format.ts`** (complete file):

```ts
/** Pure text formatting shared by the blocks (tested in test/format.test.ts). */

/** Host of a URL without "www.". */
export function domainOf(url: string): string {
  return new URL(url).hostname.replace(/^www\./, '')
}

const EARTH_RADIUS_M = 6_371_008.8

/** Great-circle distance in metres. */
export function haversineM(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad
  const dLng = (b.lng - a.lng) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h))
}

/** "820 m", "1.4 km", "23 km". */
export function formatDistance(m: number): string {
  if (m < 1000) return `${Math.round(m / 10) * 10} m`
  if (m < 10_000) return `${(m / 1000).toFixed(1)} km`
  return `${Math.round(m / 1000)} km`
}

/** "3000 BCE" / "120 CE"; year 0 does not exist in the calendar. */
export function formatYear(year: number): string {
  if (year === 0) throw new Error('year 0 does not exist; use -1 (1 BCE) or 1 (1 CE)')
  return year < 0 ? `${-year} BCE` : `${year} CE`
}

/** About six round ticks between from and to, never year 0. */
export function yearTicks(from: number, to: number): number[] {
  const raw = (to - from) / 6
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) as number
  const ticks: number[] = []
  for (let y = Math.ceil(from / step) * step; y <= to; y += step) if (y !== 0) ticks.push(y)
  return ticks
}

/** The house probability language of the papers (brief section 4) for a share in percent. */
export function verbal(p: number): string {
  if (p >= 90) return 'almost certain'
  if (p >= 75) return 'very likely'
  if (p >= 60) return 'likely'
  if (p > 40) return 'roughly even'
  if (p > 25) return 'unlikely'
  return 'very unlikely'
}

/** A number with thousands separators and at most `decimals` decimals ("1,650", "12.5"). */
export function formatNumber(value: number, decimals = 1): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: decimals })
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/format.test.ts`
Expected: `Tests  5 passed (5)`

- [ ] **Step 5: Commit**

```bash
git add video/src/format.ts video/test/format.test.ts
git commit -m "Format distances, years, numbers and probability words for the blocks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 7: The block registry: props schemas of the 18 scene blocks and registry.json

**Files:**
- Create: `video/src/blocks/icons.tsx`, `video/src/blocks/schemas.ts`, `video/scripts/registry.ts`
- Generate: `video/src/blocks/registry.json` (by `npm run registry`, committed)
- Test: `video/test/registry.test.ts`

`schemas.ts` is the single source of the registry (contract C5, table D1): each block's props describe what it receives after plan C resolves `{"$ref"}`/`{"$capture"}` (contract C6). Length limits sit where the text must fit; the rules a schema cannot express live in each block's `check()` (Tasks 13-16). Comparison blocks require their `basis` (owner rule: comparisons state their basis). Every entry also lists its `drawn` prop paths (owner decision 32: the glyph rule covers only drawn text; Task 17's `checkBlocks` and plan C's `episode check` read them), and no block has a `scale` prop (owner decision 31: linear only; ratios beyond a UnitGrid are the ScaleZoom block of Task 16). Each `drawn` list was confirmed against its component (Tasks 13-16): the enum and id values a card also draws (EvidenceCard's `paper_anchor`, ClaimBoard's `status`, ScaleDrawing's `unit`) are ASCII by their schema enum or plan C's id rule and are not listed; URLs other than ShareCard's are drawn only as their ASCII hostname.

- [ ] **Step 1: Write the failing test**

**`video/test/registry.test.ts`** (complete file):

```ts
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { CAPTURE_PROPS, REGISTRY_BLOCKS, registryJson } from '../src/blocks/schemas'
import { type Schema, unsupportedKeywords } from '../src/schema'

const REGISTRY_FILE = fileURLToPath(new URL('../src/blocks/registry.json', import.meta.url))

/** The schema a `drawn` pattern points at ('claims[].label': the label of every claim), or null. */
function schemaAt(schema: Schema, pattern: string): Schema | null {
  let at: Schema | undefined = schema
  for (const part of pattern.split('.')) {
    const key = part.endsWith('[]') ? part.slice(0, -2) : part
    at = at?.properties?.[key]
    if (at && part.endsWith('[]')) at = at.type === 'array' ? at.items : undefined
  }
  return at ?? null
}

/** Every property name anywhere in a schema. */
function propertyNames(schema: Schema): string[] {
  const own = Object.entries(schema.properties ?? {}).flatMap(([k, v]) => [k, ...propertyNames(v)])
  return schema.items ? [...own, ...propertyNames(schema.items)] : own
}

describe('blocks/registry.json (plan C contract C5)', () => {
  it('is exactly what `npm run registry` writes from schemas.ts', () => {
    expect(readFileSync(REGISTRY_FILE, 'utf-8').replace(/\r\n/g, '\n')).toBe(registryJson())
  })
  it('is {"blocks": {name: {map, platform, drawn, props}}} and nothing else', () => {
    const data = JSON.parse(readFileSync(REGISTRY_FILE, 'utf-8'))
    expect(Object.keys(data)).toEqual(['blocks'])
    for (const [name, entry] of Object.entries(data.blocks as Record<string, Record<string, unknown>>)) {
      expect(Object.keys(entry).sort(), name).toEqual(['drawn', 'map', 'platform', 'props'])
      expect(typeof entry.map, name).toBe('boolean')
      expect(typeof entry.platform, name).toBe('boolean')
      expect((entry.props as { type: string }).type, name).toBe('object')
      expect(Array.isArray(entry.drawn), name).toBe(true)
      for (const pattern of entry.drawn as unknown[]) expect(typeof pattern === 'string' && pattern.length > 0, name).toBe(true)
    }
  })
  it('lists the scene blocks of the four topic types', () => {
    expect(Object.keys(REGISTRY_BLOCKS).sort()).toEqual([
      'BarChart',
      'ClaimBoard',
      'Diagram',
      'EvidenceCard',
      'GlobeShot',
      'ListCard',
      'MapboxFlyover',
      'MapboxTopdown',
      'Meter',
      'PhotoPlate',
      'PlatformClip',
      'QuoteCard',
      'ScaleDrawing',
      'ScaleZoom',
      'ShareCard',
      'SourceViewer',
      'Timeline',
      'UnitGrid',
    ])
  })
  it('has no title card and no agent or character block (owner rules)', () => {
    for (const name of Object.keys(REGISTRY_BLOCKS)) expect(name).not.toMatch(/title|agent|character|avatar|presenter|host/i)
  })
  it('marks PlatformClip as the platform moment and the map blocks as map content', () => {
    const flagged = (key: 'map' | 'platform') =>
      Object.entries(REGISTRY_BLOCKS)
        .filter(([, e]) => e[key])
        .map(([n]) => n)
        .sort()
    expect(flagged('platform')).toEqual(['PlatformClip'])
    expect(flagged('map')).toEqual(['MapboxFlyover', 'MapboxTopdown', 'PlatformClip'])
  })
  it('uses only the JSON-schema keywords pipeline/studio/blocks.py supports', () => {
    for (const [name, entry] of Object.entries(REGISTRY_BLOCKS)) expect(unsupportedKeywords(entry.props), name).toEqual([])
  })
  it('makes every comparison block state its basis (owner rule)', () => {
    for (const name of ['ScaleDrawing', 'UnitGrid', 'BarChart', 'ScaleZoom']) expect(REGISTRY_BLOCKS[name].props.required, name).toContain('basis')
  })
  it('draws linear scales only: no block has a scale prop or a log axis (owner decision 31)', () => {
    for (const [name, entry] of Object.entries(REGISTRY_BLOCKS)) expect(propertyNames(entry.props), name).not.toContain('scale')
    expect(registryJson()).not.toMatch(/log10|logarithm/i)
  })
  it('points every drawn pattern at a string prop, never into a capture (owner decision 32)', () => {
    for (const [name, entry] of Object.entries(REGISTRY_BLOCKS)) {
      for (const pattern of entry.drawn) {
        expect(schemaAt(entry.props, pattern)?.type, `${name}: ${pattern}`).toBe('string')
        expect((CAPTURE_PROPS as readonly string[]).includes(pattern.split('.')[0]), `${name}: ${pattern}`).toBe(false)
      }
    }
    // blocks/index.ts captureStrings() walks the capture props: they are exactly the props with a capture schema
    const captures = Object.values(REGISTRY_BLOCKS).flatMap((e) =>
      Object.entries(e.props.properties ?? {})
        .filter(([, s]) => s.properties?.events !== undefined)
        .map(([k]) => k),
    )
    expect([...new Set(captures)].sort()).toEqual([...CAPTURE_PROPS].sort())
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/registry.test.ts`
Expected: FAIL with `Cannot find module '../src/blocks/schemas'`.

- [ ] **Step 3: Implement**

**`video/src/blocks/icons.tsx`** (complete file):

```tsx
/** Line icons of the ClaimBoard (24x24 viewBox, stroked in the claim's status colour). */
import React from 'react'

export const ICONS = ['weight', 'ruler', 'clock', 'globe', 'tool', 'eye', 'scroll', 'star', 'question', 'people'] as const

export type IconName = (typeof ICONS)[number]

const PATHS: Record<IconName, string> = {
  weight: 'M6 8h12l2 12H4L6 8z M9 8a3 3 0 0 1 6 0',
  ruler: 'M3 17L17 3l4 4L7 21l-4-4z M7 13l2 2 M10 10l2 2 M13 7l2 2',
  clock: 'M12 3a9 9 0 1 0 0.01 0z M12 7v5l3 3',
  globe: 'M12 3a9 9 0 1 0 0.01 0z M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18',
  tool: 'M14 6a4 4 0 0 0 5 5l-9 9-3-3 9-9a4 4 0 0 0-2-2z',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M12 9a3 3 0 1 0 0.01 0z',
  scroll: 'M7 3h11v15a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3v-2h11v2 M7 3a2 2 0 0 0-2 2v11',
  star: 'M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3z',
  question: 'M9 9a3 3 0 1 1 4 2.8c-.6.3-1 .9-1 1.6V15 M12 19v.5',
  people: 'M9 11a3 3 0 1 0 0.01 0z M3 20a6 6 0 0 1 12 0 M17 11a2.5 2.5 0 1 0 0.01 0z M16 15a5 5 0 0 1 5 5',
}

export const Icon: React.FC<{ name: IconName; color: string; size: number }> = ({ name, color, size }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d={PATHS[name]} />
  </svg>
)
```

**`video/src/blocks/schemas.ts`** (complete file):

```ts
/**
 * Props schemas of every scene block: the source of blocks/registry.json
 * (plan C contract C5, written by `npm run registry`; test/registry.test.ts
 * fails when the committed file differs). Props arrive resolved (contract C6):
 * a script's {"$ref": id} is the case-file entity, {"$capture": id} the capture
 * manifest with `path` renamed to `src`. Every src is relative to the
 * per-render public dir (media/, captures/, voice/, music/, fonts/).
 *
 * Only the keywords of src/schema.ts SUPPORTED appear here; the semantic rules a
 * schema cannot express (a box inside its image, meter values summing to 100,
 * the clip long enough for its scene) live in the blocks' check() functions.
 *
 * `drawn` lists the prop paths whose strings the block's component draws
 * (owner decision 32: the glyph rule covers only drawn text). Keys are
 * separated by '.', a key suffixed with '[]' means every element of that
 * array. Ids, src paths and URLs are not drawn (the cards draw only a URL's
 * ASCII hostname; ShareCard's url is its own drawn prop), nor is
 * SourceViewer's evidence quote: the original sits in the captured page
 * image. A capture prop (CAPTURE_PROPS) is never listed: blocks/index.ts
 * captureStrings() names the drawn strings of every capture. Plan C's
 * pipeline/studio reads `drawn` from registry.json and keeps no copy of it.
 */
import { CLAIM_STATUSES, TONES } from '../theme/colors'
import type { Schema } from '../schema'
import { ICONS } from './icons'

export type RegistryEntry = { map: boolean; platform: boolean; drawn: string[]; props: Schema }

/** The props that hold a resolved capture (C6: a script's {"$capture": id}). */
export const CAPTURE_PROPS = ['clip', 'map', 'page'] as const

const str = (minLength = 1, maxLength?: number): Schema =>
  maxLength === undefined ? { type: 'string', minLength } : { type: 'string', minLength, maxLength }
const num = (minimum?: number, maximum?: number): Schema => ({
  type: 'number',
  ...(minimum === undefined ? {} : { minimum }),
  ...(maximum === undefined ? {} : { maximum }),
})
const int = (minimum?: number, maximum?: number): Schema => ({ ...num(minimum, maximum), type: 'integer' })
const oneOf = (values: readonly string[]): Schema => ({ type: 'string', enum: values })
const arr = (items: Schema, minItems?: number, maxItems?: number): Schema => ({
  type: 'array',
  items,
  ...(minItems === undefined ? {} : { minItems }),
  ...(maxItems === undefined ? {} : { maxItems }),
})
const obj = (properties: Record<string, Schema>, required: string[] = Object.keys(properties), description?: string): Schema => ({
  type: 'object',
  additionalProperties: false,
  required,
  properties,
  ...(description === undefined ? {} : { description }),
})

const ID = str(1, 64)
const ASSET = str(1, 240)
const TONE = oneOf(TONES)
const TITLE = str(1, 48)
const BASIS: Schema = { ...str(3, 140), description: 'What the comparison is based on, always shown on screen (owner rule)' }

export const LABEL = obj({ title: str(1, 40), subtitle: str(1, 56) }, ['title'], 'Lower third over footage')

/** A case-file marker: box = [x, y, w, h] as fractions of the image, checked on a crop. */
export const MARKER = obj({ id: ID, box: arr(num(0, 1), 4, 4), label: str(1, 24) })

/** Case-file media, resolved (C6). */
export const MEDIA = obj({
  id: ID,
  src: ASSET,
  license: str(1),
  attribution: str(1),
  source_url: str(1),
  depicts: str(1),
  markers: arr(MARKER, 0, 6),
})

/** Case-file evidence, resolved (C6); length limits are per block, where the text must fit. */
export function evidenceSchema(limits: { statement?: number; quote?: number } = {}): Schema {
  return obj({
    id: ID,
    claim_id: ID,
    kind: oneOf(['fact', 'quote', 'quantity', 'date', 'image', 'place']),
    statement: str(1, limits.statement),
    source: obj({
      url: str(1),
      title: str(1),
      tier: int(0),
      license: str(0),
      quote: str(0, limits.quote),
      locator: str(0),
    }),
    paper_anchor: { type: ['string', 'null'] },
  })
}

/** Case-file claim, resolved (C6). */
export const CLAIM = obj({
  id: ID,
  label: str(1, 80),
  by: str(0, 40),
  icon: { ...oneOf(ICONS), description: 'ClaimBoard icon; the case file must use one of these names' },
  status: oneOf(CLAIM_STATUSES),
})

/** One capture manifest event (pipeline/studio/capture/manifest.py event()). */
export const EVENT: Schema = {
  type: 'object',
  additionalProperties: false,
  required: ['t', 'name'],
  properties: {
    t: num(0),
    name: str(1),
    x: num(),
    y: num(),
    box: arr(num(), 4, 4),
    target: str(1),
    label: str(1),
    url: str(1),
    title: str(0),
    lat: num(-90, 90),
    lng: num(-180, 180),
    track: {
      type: 'array',
      items: { type: ['array', 'null'], items: { type: 'number' }, minItems: 2, maxItems: 2 },
      description: 'Globe place events: the pixel [x, y] in every capture frame from the event on, null while hidden',
    },
  },
}

/** A capture, resolved (C6): manifest of pipeline/studio/capture with `path` as `src`. */
export function captureSchema(kind: 'platform' | 'globe' | 'source' | 'mapbox_topdown', still: boolean): Schema {
  return obj({
    id: ID,
    kind: oneOf([kind]),
    src: ASSET,
    fps: still ? { type: 'null' } : num(1),
    duration_s: still ? { type: 'null' } : num(0),
    width: int(2),
    height: int(2),
    events: arr(EVENT),
    credits: arr(str(1)),
  })
}

const CLIP_START: Schema = { ...num(0), description: 'Seconds into the clip where the scene starts (default 0)' }

/** One side of a ScaleZoom: a quantity drawn to the one linear scale of the frame. */
const ZOOM_QUANTITY = obj({ id: ID, label: str(1, 32), value: { ...num(0), description: 'Greater than 0, in the chart unit' } })

/** The drawn strings of a block whose only drawn prop is its lower third. */
const LABEL_DRAWN = ['label.title', 'label.subtitle']

export const REGISTRY_BLOCKS: Record<string, RegistryEntry> = {
  PhotoPlate: {
    map: false,
    platform: false,
    drawn: [...LABEL_DRAWN, 'caption', 'image.markers[].label'],
    props: obj(
      {
        image: MEDIA,
        kenBurns: { ...oneOf(['in', 'out', 'none']), description: 'Camera over the whole scene (default in)' },
        label: LABEL,
        caption: str(1, 90),
      },
      ['image'],
      'A checked photo with its markers in the same moving layer; cues show/hide/highlight <marker id>',
    ),
  },
  MapboxTopdown: {
    map: true,
    platform: false,
    drawn: LABEL_DRAWN,
    props: obj(
      {
        map: captureSchema('mapbox_topdown', true),
        lines: { ...arr(obj({ from: ID, to: ID }), 0, 4), description: 'Distance lines between two pins; the length is computed from their coordinates' },
        label: LABEL,
      },
      ['map'],
      'Exact top-down satellite frame with projected pins (orthographic, so distance lines are allowed); cues show/highlight <place id>',
    ),
  },
  PlatformClip: {
    map: true,
    platform: true,
    drawn: LABEL_DRAWN,
    props: obj(
      {
        clip: captureSchema('platform', false),
        start_s: CLIP_START,
        camera: {
          ...arr(obj({ t: num(0), cx: num(0), cy: num(0), zoom: num(1, 3) }), 1),
          description: 'Virtual camera keys on the capture clock (t in clip seconds, cx/cy in capture pixels)',
        },
        follow: { ...num(1, 2.5), description: 'Zoom the virtual camera onto each event with x/y (instead of camera)' },
        label: LABEL,
      },
      ['clip'],
      'A platform moment: the real ancientnerds.com recorded by the capture step',
    ),
  },
  GlobeShot: {
    map: false,
    platform: false,
    drawn: LABEL_DRAWN,
    props: obj(
      { clip: captureSchema('globe', false), start_s: CLIP_START, label: LABEL },
      ['clip'],
      'Our vector globe (no map credit); labelled places light up at their capture events and follow their per-frame track; cue show <place id>',
    ),
  },
  MapboxFlyover: {
    map: true,
    platform: false,
    drawn: LABEL_DRAWN,
    props: obj({ clip: captureSchema('globe', false), start_s: CLIP_START, label: LABEL }, ['clip'], 'A Mapbox fly-in or orbit take'),
  },
  SourceViewer: {
    map: false,
    platform: false,
    drawn: [],
    props: obj(
      { page: captureSchema('source', true), evidence: evidenceSchema({ statement: 160 }) },
      ['page', 'evidence'],
      'A captured source page with the quote highlighted; cue highlight <evidence id>',
    ),
  },
  EvidenceCard: {
    map: false,
    platform: false,
    drawn: ['evidence.kind', 'evidence.statement', 'evidence.source.quote', 'evidence.source.title', 'evidence.source.locator'],
    props: obj(
      { evidence: evidenceSchema({ statement: 160, quote: 260 }), image: MEDIA },
      ['evidence'],
      'One verified evidence item; cues highlight <evidence id> (quote types on), stamp <evidence id>',
    ),
  },
  QuoteCard: {
    map: false,
    platform: false,
    drawn: ['evidence.source.quote', 'evidence.source.title', 'evidence.source.locator', 'attribution'],
    props: obj(
      { evidence: evidenceSchema({ statement: 160, quote: 320 }), attribution: str(1, 60) },
      ['evidence'],
      'A verbatim passage (texts and traditions, or a page that cannot be captured); cue highlight <evidence id>',
    ),
  },
  ClaimBoard: {
    map: false,
    platform: false,
    drawn: ['title', 'claims[].label', 'claims[].by'],
    props: obj(
      { claims: arr(CLAIM, 1, 6), title: TITLE },
      ['claims'],
      'The claims under test; introduce/status cues (any scene) drive it; cue highlight <claim id>',
    ),
  },
  Meter: {
    map: false,
    platform: false,
    drawn: ['title', 'hypotheses[]', 'note'],
    props: obj(
      {
        hypotheses: arr(str(1, 40), 2, 2),
        start: { ...arr(int(0, 100), 2, 2), description: 'Split before the first meter cue; sums to 100' },
        title: TITLE,
        note: str(1, 110),
      },
      ['hypotheses', 'start'],
      'The probability meter; meter cues (any scene) move it',
    ),
  },
  ScaleDrawing: {
    map: false,
    platform: false,
    drawn: ['title', 'basis', 'objects[].label'],
    props: obj(
      {
        title: TITLE,
        unit: oneOf(['cm', 'm', 'km']),
        basis: BASIS,
        objects: arr(
          obj({
            id: ID,
            label: str(1, 24),
            shape: oneOf(['block', 'person', 'column', 'bus', 'pyramid', 'rect']),
            width: num(0),
            height: num(0),
            x: num(0),
          }),
          2,
          5,
        ),
      },
      ['title', 'unit', 'basis', 'objects'],
      'A to-scale side view on one ground line (no measuring on photos); cue show <object id>',
    ),
  },
  UnitGrid: {
    map: false,
    platform: false,
    drawn: ['title', 'unitLabel', 'basis', 'groups[].label'],
    props: obj(
      {
        title: TITLE,
        basis: BASIS,
        unitLabel: str(1, 40),
        columns: int(5, 40),
        groups: arr(obj({ id: ID, count: int(1, 400), label: str(1, 40), tone: TONE }), 1, 4),
      },
      ['title', 'basis', 'unitLabel', 'groups'],
      'Counts as lit unit squares (one block = 80 buses); cue show <group id>',
    ),
  },
  BarChart: {
    map: false,
    platform: false,
    drawn: ['title', 'unit', 'basis', 'bars[].label'],
    props: obj(
      {
        title: TITLE,
        unit: str(1, 16),
        basis: BASIS,
        bars: arr(
          obj(
            {
              id: ID,
              label: str(1, 32),
              value: {
                type: ['number', 'array'],
                minimum: 0,
                items: num(0),
                minItems: 2,
                maxItems: 2,
                description: 'a number, or [low, high] when sources differ (the bar shows the range)',
              },
              tone: TONE,
            },
            ['id', 'label', 'value'],
          ),
          2,
          8,
        ),
      },
      ['title', 'unit', 'basis', 'bars'],
      'Horizontal bars on a linear axis (frequencies, sizes); a [low, high] value is drawn as a range; cue show <bar id>',
    ),
  },
  Timeline: {
    map: false,
    platform: false,
    drawn: ['title', 'basis', 'events[].label'],
    props: obj(
      {
        title: TITLE,
        from: int(),
        to: int(),
        basis: BASIS,
        events: arr(obj({ id: ID, year: int(), label: str(1, 32), tone: TONE }), 1, 10),
      },
      ['title', 'from', 'to', 'events'],
      'A year axis (negative = BCE, no year 0); cue show <event id>',
    ),
  },
  Diagram: {
    map: false,
    platform: false,
    drawn: ['title', 'basis', 'elements[].label', 'elements[].text'],
    props: obj(
      {
        title: TITLE,
        width: num(1),
        height: num(1),
        basis: BASIS,
        elements: arr(
          obj(
            {
              id: ID,
              type: oneOf(['circle', 'line', 'arrow', 'curve', 'orbit', 'label']),
              tone: TONE,
              label: str(1, 32),
              cx: num(),
              cy: num(),
              r: num(0),
              rx: num(0),
              ry: num(0),
              period: num(0.5),
              x1: num(),
              y1: num(),
              x2: num(),
              y2: num(),
              dashed: { type: 'boolean' },
              points: arr(arr(num(), 2, 2), 2),
              x: num(),
              y: num(),
              text: str(1, 40),
            },
            ['id', 'type', 'tone'],
          ),
          1,
          16,
        ),
      },
      ['title', 'width', 'height', 'elements'],
      'NERV wireframe primitives in a width x height user space (type C topics); cue show <element id>',
    ),
  },
  ListCard: {
    map: false,
    platform: false,
    drawn: ['title', 'items[].text', 'note'],
    props: obj(
      { title: TITLE, items: arr(obj({ id: ID, text: str(1, 90) }), 1, 5), note: str(1, 110) },
      ['title', 'items'],
      'A short list, e.g. what would change our mind; cue show <item id>',
    ),
  },
  ShareCard: {
    map: false,
    platform: false,
    drawn: ['headline', 'url', 'lines[]'],
    props: obj(
      { headline: str(1, 60), url: str(1, 60), lines: arr(str(1, 80), 0, 3) },
      ['headline', 'url', 'lines'],
      'The end card: the one place the link appears in the picture',
    ),
  },
  ScaleZoom: {
    map: false,
    platform: false,
    drawn: ['title', 'unit', 'basis', 'small.label', 'large.label'],
    props: obj(
      { title: TITLE, unit: str(1, 16), basis: BASIS, small: ZOOM_QUANTITY, large: ZOOM_QUANTITY },
      ['title', 'unit', 'basis', 'small', 'large'],
      'A linear zoom-out for ratios beyond a UnitGrid (1:400), never a log axis: the small quantity drawn readable, then the camera pulls back linearly until the large one fits, the small one shrinking to a dot; cue show <small id> or show <large id> (the quantity appears)',
    ),
  },
}

/** registry.json as pipeline/studio/blocks.py reads it (contract C5). */
export function buildRegistry(): { blocks: Record<string, RegistryEntry> } {
  return { blocks: REGISTRY_BLOCKS }
}

/** The exact text of registry.json (2-space JSON and a final newline). */
export function registryJson(): string {
  return `${JSON.stringify(buildRegistry(), null, 2)}\n`
}
```

**`video/scripts/registry.ts`** (complete file):

```ts
/**
 * Writes src/blocks/registry.json (plan C contract C5) from src/blocks/schemas.ts:
 *   npm run registry
 * pipeline/studio/blocks.py reads the file at runtime; test/registry.test.ts
 * fails when the committed file differs from this output.
 */
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { buildRegistry, registryJson } from '../src/blocks/schemas'

const out = fileURLToPath(new URL('../src/blocks/registry.json', import.meta.url))
writeFileSync(out, registryJson())
console.log(`${out}: ${Object.keys(buildRegistry().blocks).length} blocks`)
```

Generate the registry:

```bash
cd video && npm run registry
```

Expected: `...\video\src\blocks\registry.json: 18 blocks` (a 2236-line JSON file; never edit it by hand).

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/registry.test.ts`
Expected: `Tests  9 passed (9)`

- [ ] **Step 5: Commit**

```bash
git add video/src/blocks/icons.tsx video/src/blocks/schemas.ts video/src/blocks/registry.json video/scripts/registry.ts video/test/registry.test.ts
git commit -m "Write the renderer's block registry for plan C from one schema source" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: timeline.json parsing and the demo timeline

**Files:**
- Create: `video/src/timeline.ts`, `video/src/cues.ts`, `video/src/fixtures/demo-timeline.json`, `video/src/fixtures/demo.ts`
- Test: `video/test/timeline.test.ts`

`parseTimeline` implements contract D3 (plan C's C8) and trusts nothing: every key, every frame, every `src` and each scene's props against its block schema; it throws with the JSON path of the first defect. It also reads the three thumbnail candidates `thumbnails: [{frame, text}]` (owner decisions 24-25: exactly 3, each an episode frame and a teaser of 2-4 words; plan C decides which frames and words may be used). The demo timeline (12 graphics-only scenes, one per block that needs no media, among them a BarChart range bar and a ScaleZoom; no media; three thumbnail candidates at frames 108, 200 and 300, all before its first verdict cue, the `status` cue at frame 330, so the committed model obeys plan C's rule that a thumbnail never shows the answer, owner decision 24) is the default props of both compositions for `npm run studio`, the fixture of the block tests and the graphics render of Task 22.

- [ ] **Step 1: Write the failing test**

**`video/test/timeline.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { REGISTRY_BLOCKS } from '../src/blocks/schemas'
import { DEMO_TIMELINE } from '../src/fixtures/demo'
import { validate } from '../src/schema'
import { assetProblem, collectSrcs, parseTimeline, sceneHasCaptions } from '../src/timeline'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = Record<string, any>
const clone = (): Json => JSON.parse(JSON.stringify(DEMO_TIMELINE))

describe('parseTimeline (plan C contract C8)', () => {
  it('accepts the demo timeline unchanged', () => {
    expect(parseTimeline(clone())).toEqual(DEMO_TIMELINE)
  })
  it('validates every demo scene against its block schema', () => {
    for (const scene of DEMO_TIMELINE.scenes) expect(validate(REGISTRY_BLOCKS[scene.block].props, scene.props), scene.id).toEqual([])
  })
  it.each([
    ['odd dimensions', (t: Json) => { t.width = 1919 }, /dimensions must be even/],
    ['wrong version', (t: Json) => { t.version = 2 }, /\$\.version: expected 1/],
    ['another frame rate', (t: Json) => { t.fps = 30 }, /\$\.fps: expected 60/],
    ['an unknown top-level key', (t: Json) => { t.intro = true }, /unknown key\(s\) intro/],
    ['a gap between scenes', (t: Json) => { t.scenes[1].from = 190 }, /\$\.scenes\[1\]\.from: expected 180/],
    ['scenes ending early', (t: Json) => { t.durationInFrames = 2300 }, /the scenes end at 2220, the episode at 2300/],
    ['an unknown block', (t: Json) => { t.scenes[0].block = 'TitleCard' }, /unknown block "TitleCard"/],
    ['invalid props', (t: Json) => { t.scenes[0].props.claims[0].icon = 'robot' }, /icon: "robot" is not one of/],
    ['an unknown prop', (t: Json) => { t.scenes[0].props.colour = 'red' }, /\.colour: not allowed/],
    ['a cue outside its scene', (t: Json) => { t.scenes[0].cues[0].frame = 400 }, /outside the scene \[0, 180\)/],
    ['an unknown cue verb', (t: Json) => { t.scenes[0].cues[0].do = 'flash' }, /"flash" is not one of/],
    ['a status cue without a status', (t: Json) => { t.scenes[1].cues[2].value = 'maybe' }, /a status cue needs one of/],
    ['a meter cue not summing to 100', (t: Json) => { t.scenes[2].cues[0].value = [80, 30] }, /two integers summing to 100/],
    ['a value on a show cue', (t: Json) => { t.scenes[4].cues[0].value = 3 }, /a show cue takes no value/],
    ['a first chapter after 0', (t: Json) => { t.chapters[0].frame = 5 }, /first chapter must start at frame 0/],
    ['a credit for a missing scene', (t: Json) => { t.credits = [{ sceneId: 'b99', text: '© x' }] }, /no scene "b99"/],
    ['overlapping captions', (t: Json) => { t.captions[1].from = 15 }, /overlaps the previous caption/],
    ['a decreasing ticker', (t: Json) => { t.ticker.evidence = [{ frame: 10, n: 2 }, { frame: 20, n: 1 }] }, /must not decrease/],
    ['a positive music gain', (t: Json) => { t.audio.music = { src: 'music/bed.wav', gainDb: 3, duck: { underNarrationDb: -12, attackFrames: 6, releaseFrames: 24 } } }, /gainDb: must be <= 0/],
    ['an absolute narration path', (t: Json) => { t.audio.narration = [{ src: 'C:/voice/b01.mp3', from: 0 }] }, /must lie under voice\//],
    ['a parent-dir path', (t: Json) => { t.audio.narration = [{ src: 'voice/../b01.mp3', from: 0 }] }, /is not a clean relative path/],
    ['two thumbnail candidates', (t: Json) => { t.thumbnails.pop() }, /expected exactly 3 thumbnail candidates, got 2/],
    ['a thumbnail past the end', (t: Json) => { t.thumbnails[0].frame = 2220 }, /\$\.thumbnails\[0\]\.frame: frame 2220 is past the end \(2220\)/],
    ['a one-word teaser', (t: Json) => { t.thumbnails[1].text = 'Buses?' }, /\$\.thumbnails\[1\]\.text: "Buses\?" has 1 word\(s\); a thumbnail teaser has 2-4/],
  ])('rejects %s', (_name, mutate, message) => {
    const t = clone()
    mutate(t)
    expect(() => parseTimeline(t)).toThrow(message)
  })
})

describe('asset paths', () => {
  it('accepts only clean paths under the four public-dir folders', () => {
    expect(assetProblem('media/stone_person.jpg')).toBeNull()
    expect(assetProblem('captures/pf1.mp4')).toBeNull()
    expect(assetProblem('fonts/orbitron-700.woff2')).toMatch(/must lie under/)
    expect(assetProblem('media//a.jpg')).toMatch(/not a clean relative path/)
  })
  it('collects every src anywhere in the timeline', () => {
    expect(collectSrcs({ a: { src: 'media/a.jpg', b: [{ src: 'captures/c.mp4' }] }, src: 'voice/b01.mp3' })).toEqual(['voice/b01.mp3', 'media/a.jpg', 'captures/c.mp4'])
  })
})

describe('frames', () => {
  it('reads the three thumbnail candidates (owner decisions 24-25) as episode frames with their teasers', () => {
    expect(DEMO_TIMELINE.thumbnails).toEqual([
      { frame: 108, text: 'Who moved it?' },
      { frame: 200, text: 'Eighty buses heavy?' },
      { frame: 300, text: 'Heavier than Giza?' },
    ])
  })
  it('knows which scenes carry hook captions', () => {
    expect(sceneHasCaptions(DEMO_TIMELINE, DEMO_TIMELINE.scenes[0])).toBe(true)
    expect(sceneHasCaptions(DEMO_TIMELINE, DEMO_TIMELINE.scenes[1])).toBe(false)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/timeline.test.ts`
Expected: FAIL with `Cannot find module '../src/fixtures/demo'`.

- [ ] **Step 3: Implement**

**`video/src/timeline.ts`** (complete file):

```ts
/**
 * timeline.json: the frame-exact episode compiled by pipeline/studio/timeline.py
 * (spec 2026-09-26 section 4.7, plan C contract C8). parseTimeline() trusts
 * nothing: it checks every field and key, validates each scene's props against
 * the block's schema (blocks/schemas.ts = registry.json) and throws with the
 * JSON path of the first defect. The block semantics and cue targets are
 * checked afterwards by blocks/index.ts checkBlocks(). calculateMetadata and the
 * node scripts both run the two, so a bad timeline fails before a frame renders.
 *
 * Frame convention: every frame number in the file is ABSOLUTE (a frame of the
 * whole episode): scenes[].from, cues[].frame, captions, ticker, chapters,
 * thumbnails and narration clips. SceneView hands blocks scene-relative cue frames.
 */
import { REGISTRY_BLOCKS } from './blocks/schemas'
import { validate } from './schema'
import { CLAIM_STATUSES, type ClaimStatus } from './theme/colors'

/** The NERV motion is timed in frames at 60 fps; pipeline/studio/script.py fixes fps at 60. */
export const FPS = 60

export const CUE_VERBS = ['show', 'hide', 'highlight', 'stamp', 'introduce', 'status', 'meter'] as const
export type CueVerb = (typeof CUE_VERBS)[number]
/** Verbs a block interprets inside its own scene; the others change episode-wide state (state.ts). */
export const LOCAL_VERBS = ['show', 'hide', 'highlight', 'stamp'] as const
export type LocalVerb = (typeof LOCAL_VERBS)[number]

export type MeterValue = [number, number]
export type Cue = { frame: number; do: CueVerb; target: string; value?: ClaimStatus | MeterValue }
export type Scene = {
  id: string
  from: number
  durationInFrames: number
  block: string
  props: Record<string, unknown>
  cues: Cue[]
}
export type NarrationClip = { src: string; from: number }
export type Duck = { underNarrationDb: number; attackFrames: number; releaseFrames: number }
export type Music = { src: string; gainDb: number; duck: Duck }
export type Caption = { text: string; from: number; to: number }
export type TickerStep = { frame: number; n: number }
export type Chapter = { title: string; frame: number }
export type Credit = { sceneId: string; text: string }
/** A thumbnail candidate (owner decisions 24-25): an episode frame and its 2-4 word teaser. */
export type ThumbnailCandidate = { frame: number; text: string }
export type Timeline = {
  version: 1
  fps: number
  width: number
  height: number
  durationInFrames: number
  audio: { narration: NarrationClip[]; music: Music | null }
  scenes: Scene[]
  captions: Caption[]
  ticker: { evidence: TickerStep[] }
  chapters: Chapter[]
  credits: Credit[]
  thumbnails: ThumbnailCandidate[]
}

/** YouTube's thumbnail A/B test takes three candidates (owner decision 24). */
export const THUMBNAIL_CANDIDATES = 3

class TimelineError extends Error {
  constructor(path: string, message: string) {
    super(`timeline.json ${path}: ${message}`)
    this.name = 'TimelineError'
  }
}

function plain(v: unknown, path: string): Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) throw new TimelineError(path, 'expected an object')
  return v as Record<string, unknown>
}
function obj(v: unknown, path: string, required: readonly string[], optional: readonly string[] = []): Record<string, unknown> {
  const o = plain(v, path)
  const missing = required.filter((k) => !(k in o))
  if (missing.length) throw new TimelineError(path, `missing ${missing.join(', ')}`)
  const unknown = Object.keys(o).filter((k) => !required.includes(k) && !optional.includes(k))
  if (unknown.length) throw new TimelineError(path, `unknown key(s) ${unknown.join(', ')}`)
  return o
}
function arr(v: unknown, path: string): unknown[] {
  if (!Array.isArray(v)) throw new TimelineError(path, 'expected an array')
  return v
}
function str(v: unknown, path: string): string {
  if (typeof v !== 'string' || v.length === 0) throw new TimelineError(path, 'expected a non-empty string')
  return v
}
function int(v: unknown, path: string, min = 0): number {
  if (typeof v !== 'number' || !Number.isInteger(v) || v < min) throw new TimelineError(path, `expected an integer >= ${min}`)
  return v
}
function num(v: unknown, path: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new TimelineError(path, 'expected a number')
  return v
}

const ASSET_DIRS = ['voice', 'captures', 'media', 'music'] as const

/** Why `src` is not a clean public-dir path under voice/, captures/, media/ or music/ (null when it is). */
export function assetProblem(src: string): string | null {
  const parts = src.split('/')
  if (!(ASSET_DIRS as readonly string[]).includes(parts[0]) || parts.length < 2) return `"${src}" must lie under ${ASSET_DIRS.map((d) => `${d}/`).join(', ')}`
  if (src.includes('\\') || src.includes(':') || parts.some((p) => p === '' || p === '.' || p === '..')) return `"${src}" is not a clean relative path`
  return null
}

/** Every string under a "src" key anywhere in `value` (props, audio). */
export function collectSrcs(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(collectSrcs)
  if (typeof value === 'object' && value !== null) {
    const o = value as Record<string, unknown>
    const own = typeof o.src === 'string' ? [o.src] : []
    return [...own, ...Object.entries(o).filter(([k]) => k !== 'src').flatMap(([, v]) => collectSrcs(v))]
  }
  return []
}

function parseCue(raw: unknown, path: string, from: number, end: number): Cue {
  const c = obj(raw, path, ['frame', 'do', 'target'], ['value'])
  const frame = int(c.frame, `${path}.frame`)
  if (frame < from || frame >= end) throw new TimelineError(path, `frame ${frame} outside the scene [${from}, ${end})`)
  const verb = str(c.do, `${path}.do`)
  if (!(CUE_VERBS as readonly string[]).includes(verb)) throw new TimelineError(`${path}.do`, `"${verb}" is not one of ${CUE_VERBS.join(', ')}`)
  const target = str(c.target, `${path}.target`)
  const cue: Cue = { frame, do: verb as CueVerb, target }
  if (verb === 'status') {
    if (!(CLAIM_STATUSES as readonly unknown[]).includes(c.value)) throw new TimelineError(`${path}.value`, `a status cue needs one of ${CLAIM_STATUSES.join(', ')}`)
    cue.value = c.value as ClaimStatus
  } else if (verb === 'meter') {
    const v = c.value
    if (target !== 'meter' || !Array.isArray(v) || v.length !== 2 || !v.every((x) => Number.isInteger(x) && x >= 0) || v[0] + v[1] !== 100) {
      throw new TimelineError(path, 'a meter cue targets "meter" with value [a, b], two integers summing to 100')
    }
    cue.value = [v[0], v[1]]
  } else if ('value' in c) {
    throw new TimelineError(`${path}.value`, `a ${verb} cue takes no value`)
  }
  return cue
}

function parseScene(raw: unknown, path: string): Scene {
  const s = obj(raw, path, ['id', 'from', 'durationInFrames', 'block', 'props', 'cues'])
  const id = str(s.id, `${path}.id`)
  const from = int(s.from, `${path}.from`)
  const durationInFrames = int(s.durationInFrames, `${path}.durationInFrames`, 1)
  const block = str(s.block, `${path}.block`)
  const entry = REGISTRY_BLOCKS[block]
  if (!entry) throw new TimelineError(`${path}.block`, `unknown block "${block}"`)
  const props = plain(s.props, `${path}.props`)
  const errors = validate(entry.props, props, `${path}.props`)
  if (errors.length) throw new TimelineError(path, `props invalid:\n  ${errors.join('\n  ')}`)
  const cues = arr(s.cues, `${path}.cues`).map((c, i) => parseCue(c, `${path}.cues[${i}]`, from, from + durationInFrames))
  return { id, from, durationInFrames, block, props, cues }
}

export function parseTimeline(raw: unknown): Timeline {
  const t = obj(raw, '$', ['version', 'fps', 'width', 'height', 'durationInFrames', 'audio', 'scenes', 'captions', 'ticker', 'chapters', 'credits', 'thumbnails'])
  if (t.version !== 1) throw new TimelineError('$.version', 'expected 1')
  if (t.fps !== FPS) throw new TimelineError('$.fps', `expected ${FPS} (the NERV motion is timed in frames at ${FPS} fps)`)
  const width = int(t.width, '$.width', 2)
  const height = int(t.height, '$.height', 2)
  if (width % 2 || height % 2) throw new TimelineError('$', `dimensions must be even, got ${width}x${height}`)
  const durationInFrames = int(t.durationInFrames, '$.durationInFrames', 1)
  const inside = (frame: number, path: string) => {
    if (frame >= durationInFrames) throw new TimelineError(path, `frame ${frame} is past the end (${durationInFrames})`)
    return frame
  }

  const audio = obj(t.audio, '$.audio', ['narration', 'music'])
  const narration = arr(audio.narration, '$.audio.narration').map((n, i) => {
    const p = `$.audio.narration[${i}]`
    const clip = obj(n, p, ['src', 'from'])
    return { src: str(clip.src, `${p}.src`), from: inside(int(clip.from, `${p}.from`), `${p}.from`) }
  })
  let music: Music | null = null
  if (audio.music !== null) {
    const m = obj(audio.music, '$.audio.music', ['src', 'gainDb', 'duck'])
    const duck = obj(m.duck, '$.audio.music.duck', ['underNarrationDb', 'attackFrames', 'releaseFrames'])
    const gainDb = num(m.gainDb, '$.audio.music.gainDb')
    if (gainDb > 0) throw new TimelineError('$.audio.music.gainDb', 'must be <= 0')
    const underNarrationDb = num(duck.underNarrationDb, '$.audio.music.duck.underNarrationDb')
    if (underNarrationDb > 0) throw new TimelineError('$.audio.music.duck.underNarrationDb', 'must be <= 0')
    music = {
      src: str(m.src, '$.audio.music.src'),
      gainDb,
      duck: {
        underNarrationDb,
        attackFrames: int(duck.attackFrames, '$.audio.music.duck.attackFrames'),
        releaseFrames: int(duck.releaseFrames, '$.audio.music.duck.releaseFrames'),
      },
    }
  }

  const scenes = arr(t.scenes, '$.scenes').map((s, i) => parseScene(s, `$.scenes[${i}]`))
  if (scenes.length === 0) throw new TimelineError('$.scenes', 'no scenes')
  const ids = new Set<string>()
  let cursor = 0
  scenes.forEach((s, i) => {
    if (ids.has(s.id)) throw new TimelineError(`$.scenes[${i}].id`, `duplicate id "${s.id}"`)
    ids.add(s.id)
    if (s.from !== cursor) throw new TimelineError(`$.scenes[${i}].from`, `expected ${cursor}: scenes follow each other without gaps or overlaps`)
    cursor = s.from + s.durationInFrames
  })
  if (cursor !== durationInFrames) throw new TimelineError('$.scenes', `the scenes end at ${cursor}, the episode at ${durationInFrames}`)

  const captions = arr(t.captions, '$.captions').map((c, i) => {
    const p = `$.captions[${i}]`
    const cap = obj(c, p, ['text', 'from', 'to'])
    const from = inside(int(cap.from, `${p}.from`), `${p}.from`)
    const to = int(cap.to, `${p}.to`)
    if (to <= from || to > durationInFrames) throw new TimelineError(p, `bad span [${from}, ${to})`)
    return { text: str(cap.text, `${p}.text`), from, to }
  })
  captions.forEach((c, i) => {
    if (i > 0 && c.from < captions[i - 1].to) throw new TimelineError(`$.captions[${i}]`, 'overlaps the previous caption')
  })

  const tickerRaw = obj(t.ticker, '$.ticker', ['evidence'])
  const evidence = arr(tickerRaw.evidence, '$.ticker.evidence').map((e, i) => {
    const p = `$.ticker.evidence[${i}]`
    const step = obj(e, p, ['frame', 'n'])
    return { frame: inside(int(step.frame, `${p}.frame`), `${p}.frame`), n: int(step.n, `${p}.n`) }
  })
  evidence.forEach((e, i) => {
    if (i > 0 && (e.frame < evidence[i - 1].frame || e.n < evidence[i - 1].n)) {
      throw new TimelineError(`$.ticker.evidence[${i}]`, 'frames and counts must not decrease')
    }
  })

  const chapters = arr(t.chapters, '$.chapters').map((c, i) => {
    const p = `$.chapters[${i}]`
    const ch = obj(c, p, ['title', 'frame'])
    return { title: str(ch.title, `${p}.title`), frame: inside(int(ch.frame, `${p}.frame`), `${p}.frame`) }
  })
  if (chapters.length && chapters[0].frame !== 0) throw new TimelineError('$.chapters[0].frame', 'the first chapter must start at frame 0')
  chapters.forEach((c, i) => {
    if (i > 0 && c.frame <= chapters[i - 1].frame) throw new TimelineError(`$.chapters[${i}].frame`, 'chapters must be in increasing order')
  })

  const credits = arr(t.credits, '$.credits').map((c, i) => {
    const p = `$.credits[${i}]`
    const cr = obj(c, p, ['sceneId', 'text'])
    const sceneId = str(cr.sceneId, `${p}.sceneId`)
    if (!ids.has(sceneId)) throw new TimelineError(`${p}.sceneId`, `no scene "${sceneId}"`)
    return { sceneId, text: str(cr.text, `${p}.text`) }
  })

  const thumbnails = arr(t.thumbnails, '$.thumbnails').map((c, i) => {
    const p = `$.thumbnails[${i}]`
    const th = obj(c, p, ['frame', 'text'])
    const text = str(th.text, `${p}.text`)
    const words = text.trim().split(/\s+/).length
    if (words < 2 || words > 4) throw new TimelineError(`${p}.text`, `"${text}" has ${words} word(s); a thumbnail teaser has 2-4`)
    return { frame: inside(int(th.frame, `${p}.frame`), `${p}.frame`), text }
  })
  if (thumbnails.length !== THUMBNAIL_CANDIDATES) throw new TimelineError('$.thumbnails', `expected exactly ${THUMBNAIL_CANDIDATES} thumbnail candidates, got ${thumbnails.length}`)

  const timeline: Timeline = { version: 1, fps: FPS, width, height, durationInFrames, audio: { narration, music }, scenes, captions, ticker: { evidence }, chapters, credits, thumbnails }
  for (const src of collectSrcs([timeline.audio, timeline.scenes])) {
    const problem = assetProblem(src)
    if (problem) throw new TimelineError('src', problem)
  }
  return timeline
}

/** True when a hook caption is on screen during part of `scene` (its block then keeps above the captions). */
export function sceneHasCaptions(timeline: Pick<Timeline, 'captions'>, scene: Pick<Scene, 'from' | 'durationInFrames'>): boolean {
  const end = scene.from + scene.durationInFrames
  return timeline.captions.some((c) => c.from < end && c.to > scene.from)
}
```

**`video/src/cues.ts`** (complete file):

```ts
/**
 * Scene-relative cue helpers for blocks. A cue fires at its frame and stays in
 * effect; blocks ask "since when" questions instead of reacting to events,
 * which keeps every frame a pure function of the frame number.
 */
import type { Cue } from './timeline'

/** A cue with its frame relative to the scene start. */
export type SceneCue = Cue

/** Frame of the first `verb` cue for `target`, or null. */
export function firstCue(cues: readonly SceneCue[], verb: string, target: string): number | null {
  let best: number | null = null
  for (const c of cues) {
    if (c.do === verb && c.target === target && (best === null || c.frame < best)) best = c.frame
  }
  return best
}

/** Frame an element appears: its first `verb` cue; without one, the block's staggered `defaultFrame`. */
export function appearFrame(cues: readonly SceneCue[], target: string, defaultFrame: number, verb = 'show'): number {
  return firstCue(cues, verb, target) ?? defaultFrame
}

/** Visible from its show cue (from the start without one) until a later hide cue. */
export function visibleAt(cues: readonly SceneCue[], target: string, frame: number): boolean {
  const start = firstCue(cues, 'show', target) ?? 0
  if (frame < start) return false
  const hides = cues.filter((c) => c.do === 'hide' && c.target === target && c.frame >= start).map((c) => c.frame)
  return hides.length === 0 || frame < Math.min(...hides)
}

/** Latest `verb` cue for `target` at or before `frame`, or null. */
export function latestCue(cues: readonly SceneCue[], verb: string, target: string, frame: number): SceneCue | null {
  let best: SceneCue | null = null
  for (const c of cues) {
    if (c.do === verb && c.target === target && c.frame <= frame && (best === null || c.frame >= best.frame)) best = c
  }
  return best
}
```

**`video/src/fixtures/demo-timeline.json`** (complete file):

```json
{
  "version": 1,
  "fps": 60,
  "width": 1920,
  "height": 1080,
  "durationInFrames": 2220,
  "audio": {
    "narration": [],
    "music": null
  },
  "scenes": [
    {
      "id": "b01",
      "from": 0,
      "durationInFrames": 180,
      "block": "ClaimBoard",
      "props": {
        "claims": [
          {
            "id": "c1",
            "label": "No one could move 800 t without machines",
            "by": "core claim",
            "icon": "weight",
            "status": "pending"
          },
          {
            "id": "c2",
            "label": "The blocks predate the Roman temple",
            "by": "popular theory",
            "icon": "clock",
            "status": "pending"
          }
        ]
      },
      "cues": [
        {
          "frame": 20,
          "do": "introduce",
          "target": "c1"
        },
        {
          "frame": 60,
          "do": "introduce",
          "target": "c2"
        },
        {
          "frame": 110,
          "do": "highlight",
          "target": "c1"
        }
      ]
    },
    {
      "id": "b02",
      "from": 180,
      "durationInFrames": 180,
      "block": "EvidenceCard",
      "props": {
        "evidence": {
          "id": "e1",
          "claim_id": "c1",
          "kind": "quantity",
          "statement": "The Stone of the Pregnant Woman weighs about 1,000 tonnes.",
          "source": {
            "url": "https://www.dainst.org/baalbek-report",
            "title": "Baalbek: the largest stone blocks of antiquity",
            "tier": 1,
            "license": "",
            "quote": "the block, measuring 19.6 m in length, is estimated to weigh 1,650 tonnes",
            "locator": "section 2"
          },
          "paper_anchor": "ev-01"
        }
      },
      "cues": [
        {
          "frame": 200,
          "do": "highlight",
          "target": "e1"
        },
        {
          "frame": 300,
          "do": "stamp",
          "target": "e1"
        },
        {
          "frame": 330,
          "do": "status",
          "target": "c1",
          "value": "weakened"
        }
      ]
    },
    {
      "id": "b03",
      "from": 360,
      "durationInFrames": 180,
      "block": "Meter",
      "props": {
        "hypotheses": [
          "Roman engineers",
          "A lost older civilization"
        ],
        "start": [
          50,
          50
        ],
        "note": "Roman tool marks and unfinished blocks in the quarry"
      },
      "cues": [
        {
          "frame": 420,
          "do": "meter",
          "target": "meter",
          "value": [
            80,
            20
          ]
        }
      ]
    },
    {
      "id": "b04",
      "from": 540,
      "durationInFrames": 180,
      "block": "QuoteCard",
      "props": {
        "evidence": {
          "id": "e2",
          "claim_id": "c1",
          "kind": "quote",
          "statement": "The Stone of the Pregnant Woman weighs about 1,000 tonnes.",
          "source": {
            "url": "https://www.dainst.org/baalbek-report",
            "title": "Baalbek: the largest stone blocks of antiquity",
            "tier": 1,
            "license": "",
            "quote": "the block, measuring 19.6 m in length, is estimated to weigh 1,650 tonnes",
            "locator": "section 2"
          },
          "paper_anchor": "ev-01"
        },
        "attribution": "German Archaeological Institute"
      },
      "cues": [
        {
          "frame": 550,
          "do": "highlight",
          "target": "e2"
        }
      ]
    },
    {
      "id": "b05",
      "from": 720,
      "durationInFrames": 180,
      "block": "ScaleDrawing",
      "props": {
        "title": "How big is the stone?",
        "unit": "m",
        "basis": "block 20.5 m x 4 m, DAI 2014; person 1.75 m; city bus 12 m",
        "objects": [
          {
            "id": "q1",
            "label": "The block",
            "shape": "block",
            "width": 20.5,
            "height": 4,
            "x": 0
          },
          {
            "id": "o2",
            "label": "Person",
            "shape": "person",
            "width": 0.5,
            "height": 1.75,
            "x": 21.5
          },
          {
            "id": "o3",
            "label": "City bus",
            "shape": "bus",
            "width": 12,
            "height": 3.2,
            "x": 23.5
          }
        ]
      },
      "cues": [
        {
          "frame": 750,
          "do": "show",
          "target": "q1"
        }
      ]
    },
    {
      "id": "b06",
      "from": 900,
      "durationInFrames": 180,
      "block": "UnitGrid",
      "props": {
        "title": "How heavy is 1,000 tonnes?",
        "basis": "city bus about 12.5 t (MAN Lion’s City)",
        "unitLabel": "one city bus",
        "groups": [
          {
            "id": "q2",
            "count": 80,
            "label": "city buses",
            "tone": "accent"
          }
        ]
      },
      "cues": []
    },
    {
      "id": "b07",
      "from": 1080,
      "durationInFrames": 180,
      "block": "BarChart",
      "props": {
        "title": "The heaviest moved stones",
        "unit": "t",
        "basis": "published weight estimates",
        "bars": [
          {
            "id": "q3",
            "label": "Thunder Stone",
            "value": 1250
          },
          {
            "id": "q4",
            "label": "Stone of the Pregnant Woman",
            "value": [
              1000,
              1650
            ],
            "tone": "warn"
          },
          {
            "id": "q5",
            "label": "Western Wall stone",
            "value": 570,
            "tone": "info"
          }
        ]
      },
      "cues": []
    },
    {
      "id": "b08",
      "from": 1260,
      "durationInFrames": 180,
      "block": "Timeline",
      "props": {
        "title": "Building phases",
        "from": -3000,
        "to": 300,
        "basis": "excavation reports, DAI 2004-2014",
        "events": [
          {
            "id": "q6",
            "year": -2900,
            "label": "first settlement",
            "tone": "muted"
          },
          {
            "id": "q7",
            "year": -15,
            "label": "Jupiter temple begun",
            "tone": "accent"
          },
          {
            "id": "q8",
            "year": 60,
            "label": "podium finished",
            "tone": "warn"
          }
        ]
      },
      "cues": []
    },
    {
      "id": "b09",
      "from": 1440,
      "durationInFrames": 180,
      "block": "Diagram",
      "props": {
        "title": "Lever and ramp",
        "width": 100,
        "height": 50,
        "basis": "forces not to scale",
        "elements": [
          {
            "id": "d1",
            "type": "line",
            "tone": "muted",
            "x1": 5,
            "y1": 45,
            "x2": 95,
            "y2": 45
          },
          {
            "id": "d2",
            "type": "circle",
            "tone": "accent",
            "cx": 30,
            "cy": 35,
            "r": 10,
            "label": "block"
          },
          {
            "id": "d3",
            "type": "arrow",
            "tone": "warn",
            "x1": 60,
            "y1": 20,
            "x2": 42,
            "y2": 30,
            "label": "pull"
          }
        ]
      },
      "cues": []
    },
    {
      "id": "b10",
      "from": 1620,
      "durationInFrames": 180,
      "block": "ListCard",
      "props": {
        "title": "What would change our mind",
        "items": [
          {
            "id": "i1",
            "text": "A quarry mark older than the Roman phase"
          },
          {
            "id": "i2",
            "text": "A transport route no Roman sled could take"
          }
        ],
        "note": "Neither has been found in forty years of excavation."
      },
      "cues": []
    },
    {
      "id": "b11",
      "from": 1800,
      "durationInFrames": 240,
      "block": "ScaleZoom",
      "props": {
        "title": "One block, one pyramid",
        "unit": "t",
        "basis": "block about 1,000 t; Great Pyramid about 6 million t (common estimate)",
        "small": {
          "id": "q9",
          "label": "Stone of the Pregnant Woman",
          "value": 1000
        },
        "large": {
          "id": "q10",
          "label": "Great Pyramid of Giza",
          "value": 6000000
        }
      },
      "cues": [
        {
          "frame": 1850,
          "do": "show",
          "target": "q10"
        }
      ]
    },
    {
      "id": "b12",
      "from": 2040,
      "durationInFrames": 180,
      "block": "ShareCard",
      "props": {
        "headline": "The full case file",
        "url": "ancientnerds.com",
        "lines": [
          "Every source, every claim, checked"
        ]
      },
      "cues": []
    }
  ],
  "captions": [
    {
      "text": "THIS",
      "from": 12,
      "to": 24
    },
    {
      "text": "STONE",
      "from": 24,
      "to": 40
    },
    {
      "text": "WEIGHS",
      "from": 40,
      "to": 56
    },
    {
      "text": "ABOUT",
      "from": 56,
      "to": 70
    },
    {
      "text": "1,000",
      "from": 70,
      "to": 90
    },
    {
      "text": "TONNES.",
      "from": 90,
      "to": 110
    }
  ],
  "ticker": {
    "evidence": [
      {
        "frame": 0,
        "n": 0
      },
      {
        "frame": 180,
        "n": 1
      }
    ]
  },
  "chapters": [
    {
      "title": "The stone",
      "frame": 0
    },
    {
      "title": "The evidence",
      "frame": 180
    },
    {
      "title": "The verdict",
      "frame": 1620
    }
  ],
  "credits": [],
  "thumbnails": [
    {
      "frame": 108,
      "text": "Who moved it?"
    },
    {
      "frame": 200,
      "text": "Eighty buses heavy?"
    },
    {
      "frame": 300,
      "text": "Heavier than Giza?"
    }
  ]
}
```

**`video/src/fixtures/demo.ts`** (complete file):

```ts
/**
 * Graphics-only demo timeline (demo-timeline.json): the default props of both
 * compositions, so `npm run studio` (public dir = ancient-nerds-map/public,
 * fonts only) shows every block that needs no media. The timeline and block
 * tests use it as fixture. Evidence and claims mirror the Baalbek pilot's shapes.
 */
import { parseTimeline } from '../timeline'
import demo from './demo-timeline.json'

export const DEMO_TIMELINE = parseTimeline(demo)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/timeline.test.ts`
Expected: `Tests  30 passed (30)`

- [ ] **Step 5: Commit**

```bash
git add video/src/timeline.ts video/src/cues.ts video/src/fixtures/demo-timeline.json video/src/fixtures/demo.ts video/test/timeline.test.ts
git commit -m "Parse timeline.json strictly and add the graphics-only demo timeline" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 9: Episode-wide claim and meter state

**Files:**
- Create: `video/src/state.ts`
- Test: `video/test/state.test.ts`

A claim is introduced once and changes status over the episode; the meter moves. The cues that change them can sit in any scene (plan C places a `status` cue on the beat whose word triggers it, e.g. in an EvidenceCard scene), so a ClaimBoard or Meter shown later reflects everything cued before it. The state is a pure function of the absolute frame, built once per timeline.

- [ ] **Step 1: Write the failing test**

**`video/test/state.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { METER_ROLL_FRAMES, buildState, claimStatusAt, meterAt } from '../src/state'
import type { Scene } from '../src/timeline'

const scene = (id: string, from: number, cues: Scene['cues']): Scene => ({ id, from, durationInFrames: 100, block: 'ListCard', props: {}, cues })

const STATE = buildState([
  scene('b01', 0, [
    { frame: 20, do: 'introduce', target: 'c1' },
    { frame: 50, do: 'meter', target: 'meter', value: [60, 40] },
  ]),
  scene('b02', 100, [
    { frame: 150, do: 'status', target: 'c1', value: 'weakened' },
    { frame: 120, do: 'introduce', target: 'c1' },
  ]),
  scene('b03', 200, [
    { frame: 250, do: 'status', target: 'c1', value: 'refuted' },
    { frame: 260, do: 'meter', target: 'meter', value: [90, 10] },
  ]),
])

describe('episode-wide cue state', () => {
  it('keeps the first introduce cue of a claim', () => {
    expect(STATE.introduced.get('c1')).toBe(20)
    expect(STATE.introduced.has('c2')).toBe(false)
  })
  it('gives a claim the latest status at or before a frame, whichever scene set it', () => {
    expect(claimStatusAt(STATE, 'c1', 'pending', 100)).toEqual({ status: 'pending', since: null })
    expect(claimStatusAt(STATE, 'c1', 'pending', 150)).toEqual({ status: 'weakened', since: 150 })
    expect(claimStatusAt(STATE, 'c1', 'pending', 999)).toEqual({ status: 'refuted', since: 250 })
  })
  it('rolls the meter from the start split through every move', () => {
    expect(meterAt(STATE, [50, 50], 10)).toEqual({ a: 50, since: null })
    expect(meterAt(STATE, [50, 50], 50 + METER_ROLL_FRAMES)).toEqual({ a: 60, since: 50 })
    const rolling = meterAt(STATE, [50, 50], 270)
    expect(rolling.since).toBe(260)
    expect(rolling.a).toBeGreaterThan(60)
    expect(rolling.a).toBeLessThan(90)
    expect(meterAt(STATE, [50, 50], 400).a).toBeCloseTo(90)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/state.test.ts`
Expected: FAIL with `Cannot find module '../src/state'`.

- [ ] **Step 3: Implement**

**`video/src/state.ts`** (complete file):

```ts
/**
 * Episode-wide state carried by the global cues (plan C contract C8): a claim
 * is introduced once and changes status over the episode, the probability
 * meter moves; the ClaimBoard or Meter shown later reflects everything cued
 * before it, whichever scene the cue sat in. Pure functions of the absolute
 * frame, precomputed once per timeline.
 */
import { progress } from './motion'
import type { ClaimStatus } from './theme/colors'
import type { MeterValue, Scene } from './timeline'

export type StatusChange = { frame: number; value: ClaimStatus }
export type MeterMove = { frame: number; value: MeterValue }
export type EpisodeState = {
  /** Claim id -> the frame of its first introduce cue. */
  introduced: ReadonlyMap<string, number>
  /** Claim id -> its status cues in frame order. */
  statuses: ReadonlyMap<string, readonly StatusChange[]>
  /** Meter cues in frame order. */
  meter: readonly MeterMove[]
}

/** Frames the meter takes to roll to a new split. */
export const METER_ROLL_FRAMES = 36

export function buildState(scenes: readonly Scene[]): EpisodeState {
  const introduced = new Map<string, number>()
  const statuses = new Map<string, StatusChange[]>()
  const meter: MeterMove[] = []
  const cues = scenes.flatMap((s) => s.cues).sort((a, b) => a.frame - b.frame)
  for (const cue of cues) {
    if (cue.do === 'introduce' && !introduced.has(cue.target)) introduced.set(cue.target, cue.frame)
    if (cue.do === 'status') statuses.set(cue.target, [...(statuses.get(cue.target) ?? []), { frame: cue.frame, value: cue.value as ClaimStatus }])
    if (cue.do === 'meter') meter.push({ frame: cue.frame, value: cue.value as MeterValue })
  }
  return { introduced, statuses, meter }
}

/** A claim's status at an absolute frame: the latest status cue at or before it, else the case file's. */
export function claimStatusAt(state: EpisodeState, id: string, initial: ClaimStatus, frame: number): { status: ClaimStatus; since: number | null } {
  let current: { status: ClaimStatus; since: number | null } = { status: initial, since: null }
  for (const change of state.statuses.get(id) ?? []) {
    if (change.frame <= frame) current = { status: change.value, since: change.frame }
  }
  return current
}

/** Share of hypothesis A at an absolute frame (fractional while rolling) and the frame of the last move. */
export function meterAt(state: EpisodeState, start: MeterValue, frame: number): { a: number; since: number | null } {
  let a = start[0]
  let since: number | null = null
  for (const move of state.meter) {
    if (move.frame > frame) break
    a = a + (move.value[0] - a) * progress(frame, move.frame, METER_ROLL_FRAMES)
    since = move.frame
  }
  return { a, since }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/state.test.ts`
Expected: `Tests  3 passed (3)`

- [ ] **Step 5: Commit**

```bash
git add video/src/state.ts video/test/state.test.ts
git commit -m "Derive claim statuses and the probability meter from the episode's cues" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 10: Music ducking, hook caption lines, the evidence counter and credit lines

**Files:**
- Create: `video/src/audio.ts`, `video/src/captions.ts`
- Test: `video/test/audio.test.ts`, `video/test/captions.test.ts`

Remotion has no built-in ducking: the music bed gets a per-frame volume callback that drops by `underNarrationDb` under every narration span with linear attack and release ramps. Hook captions (owner rule: burned in only during the hook) come as one entry per display word; they are grouped into lines of at most four words and at most `HOOK_LINE_MAX_CHARS` (24) characters, broken at punctuation and at pauses. The character budget exists because HookCaptions draws a line on one row (`nowrap`) in the 1440-px caption zone in `heading(64)`: Orbitron 700, upper case, 0.06em spacing. Measured with fontTools on `ancient-nerds-map/public/fonts/orbitron-700.woff2` at 64 px plus 0.06em per character (2026-09-27): a capital averages 56 px, so about 26 capitals fit. 'THIS STONE WEIGHS ABOUT' is 1126 px and 'ARCHAEOLOGISTS FOUND SOMETHING IMPOSSIBLE' is 2046 px. Over six realistic hook sentences, 5 of the 18 lines that four-word grouping builds are wider than 1440 px; with the 24-character budget the widest line is 1220 px. Four words alone would let ordinary hook lines overflow, and lint.ts would then refuse the render only after voice, capture and timeline had run. A run of wide capitals can still exceed the zone (24 × `M` is 1518 px), and lint.ts reports that as an `overflow`. A single word longer than 24 characters is the one line no break can shorten: plan C's script check refuses such a hook word before voice (it reads this constant). lint.ts remains the final guard for unusually wide letter runs.

- [ ] **Step 1: Write the failing tests**

**`video/test/audio.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { dbToGain, duckAmount, musicVolume, narrationSpans } from '../src/audio'

const music = { src: 'music/bed.wav', gainDb: -8, duck: { underNarrationDb: -12, attackFrames: 6, releaseFrames: 24 } }

describe('narrationSpans', () => {
  it('turns clip starts and measured seconds into frame spans (rounded up)', () => {
    expect(narrationSpans([{ src: 'voice/b01.mp3', from: 0 }, { src: 'voice/b02.mp3', from: 300 }], [2.01, 3], 60)).toEqual([
      { from: 0, to: 121 },
      { from: 300, to: 480 },
    ])
  })
  it('refuses a missing or zero duration', () => {
    expect(() => narrationSpans([{ src: 'voice/b01.mp3', from: 0 }], [0], 60)).toThrow(/has no duration/)
    expect(() => narrationSpans([{ src: 'voice/b01.mp3', from: 0 }], [], 60)).toThrow(/1 clips but 0 durations/)
  })
})

describe('ducking', () => {
  const spans = [{ from: 100, to: 200 }]
  it('ramps down over attackFrames, holds, then releases over releaseFrames', () => {
    expect(duckAmount(50, spans, 6, 24)).toBe(0)
    expect(duckAmount(97, spans, 6, 24)).toBeCloseTo(0.5)
    expect(duckAmount(150, spans, 6, 24)).toBe(1)
    expect(duckAmount(211, spans, 6, 24)).toBeCloseTo(0.5)
    expect(duckAmount(224, spans, 6, 24)).toBe(0)
  })
  it('sits at gainDb in pauses and gainDb + underNarrationDb under speech', () => {
    expect(dbToGain(-20)).toBeCloseTo(0.1)
    expect(musicVolume(0, music, spans)).toBeCloseTo(dbToGain(-8))
    expect(musicVolume(150, music, spans)).toBeCloseTo(dbToGain(-20))
  })
})
```

**`video/test/captions.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { HOOK_LINE_MAX_CHARS, captionLines, lineAt, mergeCredits, tickerAt } from '../src/captions'

const w = (text: string, from: number, to: number) => ({ text, from, to })
const texts = (lines: ReturnType<typeof captionLines>) => lines.map((l) => l.words.map((x) => x.text).join(' '))

describe('captionLines', () => {
  it('breaks after four words, after punctuation and at long pauses', () => {
    const lines = captionLines([
      w('THIS', 0, 10), w('STONE', 10, 20), w('WEIGHS', 20, 30), w('ABOUT', 30, 40), w('1,000', 40, 55), w('TONNES.', 55, 70),
      w('NOBODY', 100, 110), w('MOVED', 110, 120),
    ])
    expect(texts(lines)).toEqual(['THIS STONE WEIGHS ABOUT', '1,000 TONNES.', 'NOBODY MOVED'])
    expect(lines[1]).toMatchObject({ from: 40, to: 70 })
  })
  it('breaks before a word that would make the line longer than 24 characters (one row of the caption zone)', () => {
    expect(HOOK_LINE_MAX_CHARS).toBe(24)
    const lines = captionLines([w('ARCHAEOLOGISTS', 0, 20), w('FOUND', 20, 30), w('SOMETHING', 30, 45), w('IMPOSSIBLE', 45, 60)])
    expect(texts(lines)).toEqual(['ARCHAEOLOGISTS FOUND', 'SOMETHING IMPOSSIBLE'])
  })
})

describe('lineAt', () => {
  const lines = captionLines([w('ONE', 0, 10), w('TWO.', 10, 20), w('THREE', 25, 40)])
  it('holds a line until the next starts or 10 frames after its last word', () => {
    expect(lineAt(lines, 5)?.words[0].text).toBe('ONE')
    expect(lineAt(lines, 24)?.words[0].text).toBe('ONE')
    expect(lineAt(lines, 25)?.words[0].text).toBe('THREE')
    expect(lineAt(lines, 49)?.words[0].text).toBe('THREE')
    expect(lineAt(lines, 50)).toBeNull()
  })
})

describe('tickerAt', () => {
  it('counts the evidence shown so far and remembers the change', () => {
    const steps = [{ frame: 0, n: 0 }, { frame: 100, n: 1 }, { frame: 300, n: 3 }]
    expect(tickerAt(steps, 50)).toEqual({ n: 0, previous: 0, since: -1 })
    expect(tickerAt(steps, 150)).toEqual({ n: 1, previous: 0, since: 100 })
    expect(tickerAt(steps, 300)).toEqual({ n: 3, previous: 1, since: 300 })
  })
})

describe('mergeCredits', () => {
  it('merges repeated © parts and puts other credits first', () => {
    expect(mergeCredits(['© Mapbox © OpenStreetMap © Maxar', '© Mapbox © Maxar'])).toBe('© Mapbox © OpenStreetMap © Maxar')
    expect(mergeCredits(['© Mapbox © Maxar', 'Photo: Jane Doe (CC BY-SA 4.0)'])).toBe('Photo: Jane Doe (CC BY-SA 4.0) · © Mapbox © Maxar')
    expect(mergeCredits([])).toBe('')
  })
})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd video && npx vitest run test/audio.test.ts test/captions.test.ts`
Expected: FAIL with `Cannot find module '../src/audio'` and `Cannot find module '../src/captions'`.

- [ ] **Step 3: Implement**

**`video/src/audio.ts`** (complete file):

```ts
/**
 * Frame math of the audio tracks. Narration clips carry only their start
 * frame in timeline.json; calculateMetadata measures each clip's length and
 * hands narrationSpans() the durations. The music bed ducks under every span.
 */
import type { Music, NarrationClip } from './timeline'

/** [from, to) in absolute frames. */
export type Span = { from: number; to: number }

export function dbToGain(db: number): number {
  return 10 ** (db / 20)
}

export function narrationSpans(clips: readonly NarrationClip[], durationsS: readonly number[], fps: number): Span[] {
  if (clips.length !== durationsS.length) throw new Error(`narrationSpans: ${clips.length} clips but ${durationsS.length} durations`)
  return clips.map((c, i) => {
    const d = durationsS[i]
    if (!(d > 0)) throw new Error(`narration clip ${c.src} has no duration`)
    return { from: c.from, to: c.from + Math.ceil(d * fps) }
  })
}

/** 0 = no ducking, 1 = fully ducked; linear ramps of attackFrames before and releaseFrames after each span. */
export function duckAmount(frame: number, spans: readonly Span[], attackFrames: number, releaseFrames: number): number {
  let amount = 0
  for (const s of spans) {
    let a = 0
    if (frame >= s.from && frame < s.to) a = 1
    else if (frame < s.from && frame >= s.from - attackFrames) a = 1 - (s.from - frame) / Math.max(attackFrames, 1)
    else if (frame >= s.to && frame < s.to + releaseFrames) a = 1 - (frame - s.to + 1) / Math.max(releaseFrames, 1)
    amount = Math.max(amount, a)
  }
  return amount
}

/** Linear volume of the music bed at an absolute frame: gainDb in the pauses, gainDb + underNarrationDb under speech. */
export function musicVolume(frame: number, music: Music, spans: readonly Span[]): number {
  const duck = duckAmount(frame, spans, music.duck.attackFrames, music.duck.releaseFrames)
  return dbToGain(music.gainDb + duck * music.duck.underNarrationDb)
}
```

**`video/src/captions.ts`** (complete file):

```ts
/**
 * Hook captions: timeline.captions holds one entry per displayed word
 * ({text, from, to}, the script's spelling, uppercase). They are grouped into
 * short lines; a line stays up until the next one starts (or HOLD_FRAMES after
 * its last word) and the word being spoken is highlighted. Also the evidence
 * ticker's counter and the in-frame credit line.
 */
import type { Caption, TickerStep } from './timeline'

export type CaptionLine = { words: Caption[]; from: number; to: number }

/**
 * The longest hook caption line in characters, its words joined by single spaces.
 * HookCaptions draws a line on one row (nowrap) in ZONES.caption, 1440 px wide, in
 * heading(64): Orbitron 700, upper case, 0.06em spacing, about 56 px per capital.
 * Plan C's script check reads this line with a regex and refuses a hook word longer
 * than this, the one line no break can shorten; lint.ts stays the final guard.
 */
export const HOOK_LINE_MAX_CHARS = 24
const MAX_WORDS = 4
/** A pause longer than this between two words starts a new line. */
const GAP_FRAMES = 12
const HOLD_FRAMES = 10

/** Characters of a line: its words joined by single spaces. */
const lineChars = (words: readonly Caption[]) => words.map((w) => w.text).join(' ').length

export function captionLines(captions: readonly Caption[], maxWords = MAX_WORDS, maxChars = HOOK_LINE_MAX_CHARS): CaptionLine[] {
  const lines: CaptionLine[] = []
  let current: Caption[] = []
  const flush = () => {
    if (current.length) lines.push({ words: current, from: current[0].from, to: current[current.length - 1].to })
    current = []
  }
  captions.forEach((c, i) => {
    const prev = captions[i - 1]
    const full = current.length >= maxWords || lineChars([...current, c]) > maxChars
    if (current.length && (full || c.from - prev.to > GAP_FRAMES)) flush()
    current.push(c)
    if (/[.!?,;:]$/.test(c.text)) flush()
  })
  flush()
  return lines
}

/** The line on screen at `frame`, or null. */
export function lineAt(lines: readonly CaptionLine[], frame: number): CaptionLine | null {
  for (let i = 0; i < lines.length; i++) {
    const next = lines[i + 1]
    const end = Math.min(lines[i].to + HOLD_FRAMES, next ? next.from : Number.POSITIVE_INFINITY)
    if (frame >= lines[i].from && frame < end) return lines[i]
  }
  return null
}

/** Evidence counter at `frame`: the count so far, the count before the last change and when it changed. */
export function tickerAt(steps: readonly TickerStep[], frame: number): { n: number; previous: number; since: number } {
  let n = 0
  let previous = 0
  let since = -1
  for (const s of steps) {
    if (s.frame > frame) break
    if (s.n !== n) {
      previous = n
      since = s.frame
    }
    n = s.n
  }
  return { n, previous, since }
}

/**
 * One credit line from a scene's credits. "©" statements are split into their
 * parts and repeated parts dropped, so the capture's "© Mapbox © OpenStreetMap
 * © Maxar" and the script's "© Mapbox © Maxar" read "© Mapbox © OpenStreetMap
 * © Maxar"; other credits (photo licences, source pages) come first, separated
 * by " · ".
 */
export function mergeCredits(texts: readonly string[]): string {
  const others: string[] = []
  const copyrights: string[] = []
  for (const text of texts) {
    for (const part of text.split(/(?=©)/)) {
      const clean = part.trim()
      const list = clean.startsWith('©') ? copyrights : others
      if (clean && !list.includes(clean)) list.push(clean)
    }
  }
  return [...others, copyrights.join(' ')].filter(Boolean).join(' · ')
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd video && npx vitest run test/audio.test.ts test/captions.test.ts`
Expected: `Tests  9 passed (9)`

- [ ] **Step 5: Commit**

```bash
git add video/src/audio.ts video/src/captions.ts video/test/audio.test.ts video/test/captions.test.ts
git commit -m "Duck the music under narration and group the hook captions into short lines" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 11: Episode context, measurements, the GPU probe and the lint-mode layout guard

**Files:**
- Create: `video/src/context.ts`, `video/src/media.ts`, `video/src/gpu.ts`, `video/src/layout/LayoutBox.tsx`, `video/src/layout/LayoutGuard.tsx`, `video/test/gpu/vitest.config.ts`, `video/test/gpu/guardFixture.tsx`
- Test: `video/test/guard.test.ts`; `video/test/gpu/guard.gpu.ts` (real browser on the RTX 3080, workstation only: `npm run test:gpu`)

`LayoutBox` measures its element after each frame's render (a layout effect, so before Remotion takes the screenshot) and registers the box only in lint mode; `LayoutGuard`, rendered last, runs `findViolations` over the frame's boxes and prints each violation as one JSON line with `console.error`, which `lint.ts` collects (spec 4.8). `gpu.ts` reads the render browser's WebGL renderer for the GPU proof (spec 4.11); `media.ts` measures narration lengths and image sizes before the first frame.

Lint mode measures only in the brand fonts (review fix 2026-09-27). Remotion 4.0.529 mounts the composition (`remotion_setBundleMode`, `make-page.js`) without waiting for delayRender handles, and `remotion_setFrame` to the frame a tab already shows returns the same state (`TimelineContext.js`), so nothing renders again. `loadFont` adds a face to `document.fonts` only after its fetch and `load()`. A measurement at mount would therefore judge the first frame of every render tab (its `initialFrame`), and so the whole one-frame Thumbnail lint, in whatever fonts had arrived. Measured in chrome-headless-shell with the Thumbnail's teaser box (1368x332, `heading(104)`): `WHO ENGINEERED BAALBEK MONOLITHS?` takes two lines in the fallback font and three in Orbitron. So a lint-mode `LayoutProvider` holds a `delayRender` handle from mount until `brandFontsReady()` (Task 2) resolves. It then renders again with `fontsReady`, so every `LayoutBox` measures and `LayoutGuard` reports in that commit, and it releases the handle in its own layout effect, which runs after its children's. The context is `{registry, fontsReady}`, read with `useLayoutState()`. `Registry.set` refuses a box on a disabled registry, and `LayoutGuard` refuses to render under one.

The vitest suite covers only the pure helpers, so Step 5 proves in a real browser that the gate fires. `test/gpu/guard.gpu.ts` bundles `guardFixture.tsx` with the seven font files and holds the font files back 2.5 s. It opens every browser with `gl: 'angle'` and requires the NVIDIA renderer string, then renders the way `lint.ts` does (`renderFrames`, scale 0.5, violations from `onBrowserLog`). It requires exactly the planted lines, as `violationLine` builds them, on all 6 frames with concurrency 2: `teaser` overflow, `edge` outside-safe and `captions`/`lt` overlap, plus `drop` in the controls from frame 3. It requires no lines outside lint mode. On a Thumbnail-like one-frame composition it requires exactly the teaser's overflow: the scene under a disabled registry is not reported, and a fitting two-line teaser gives nothing. It needs Tasks 2 (`type.ts`, `fontCoverage.ts`) and 4 (`zones.ts`, `geometry.ts`), both earlier.

- [ ] **Step 1: Write the failing test**

**`video/test/guard.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { imageSize } from '../src/context'
import { Registry } from '../src/layout/LayoutBox'
import { VIOLATION_TYPE, violationLine } from '../src/layout/LayoutGuard'

describe('LayoutBox registry (lint mode)', () => {
  it('keeps the latest box per id and tracks clipped text', () => {
    const registry = new Registry(true)
    registry.set({ id: 'b01:title', kind: 'text', rect: { x: 0, y: 0, w: 10, h: 10 }, allow: [] }, true)
    registry.set({ id: 'b01:title', kind: 'text', rect: { x: 5, y: 5, w: 10, h: 10 }, allow: [] }, false)
    expect(registry.boxes.get('b01:title')?.rect.x).toBe(5)
    expect(registry.overflow.size).toBe(0)
    registry.set({ id: 'b01:quote', kind: 'text', rect: { x: 0, y: 0, w: 1, h: 1 }, allow: [] }, true)
    expect([...registry.overflow]).toEqual(['b01:quote'])
    registry.remove('b01:quote')
    expect(registry.boxes.has('b01:quote') || registry.overflow.has('b01:quote')).toBe(false)
  })
  it('refuses a box outside lint mode and keeps nothing', () => {
    const registry = new Registry(false)
    expect(() => registry.set({ id: 'b01:title', kind: 'text', rect: { x: 0, y: 0, w: 10, h: 10 }, allow: [] }, true)).toThrow(
      'LayoutBox b01:title was measured outside lint mode',
    )
    expect(registry.boxes.size + registry.overflow.size).toBe(0)
  })
})

describe('LayoutGuard lines', () => {
  it('writes one JSON line per violation: {type, frame, a, b, reason}', () => {
    expect(JSON.parse(violationLine(123, { a: 'captions', b: 'b01:lt', reason: 'overlap' }))).toEqual({
      type: VIOLATION_TYPE,
      frame: 123,
      a: 'captions',
      b: 'b01:lt',
      reason: 'overlap',
    })
    expect(violationLine(7, { a: 'b03:statement', b: null, reason: 'overflow' })).toBe(
      '{"type":"layout-violation","frame":7,"a":"b03:statement","b":null,"reason":"overflow"}',
    )
  })
})

describe('imageSize', () => {
  it('returns the measured size and refuses an unmeasured image', () => {
    expect(imageSize({ 'media/a.jpg': [1600, 1200] }, 'media/a.jpg')).toEqual([1600, 1200])
    expect(() => imageSize({}, 'media/b.jpg')).toThrow(/media\/b.jpg was not measured/)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/guard.test.ts`
Expected: FAIL with `Cannot find module '../src/context'`.

- [ ] **Step 3: Implement**

**`video/src/context.ts`** (complete file):

```ts
/**
 * What every block may read besides its own props: the episode-wide cue state,
 * the measured pixel sizes of the images (calculateMetadata measures them in
 * the browser, so a PhotoPlate can place fractional marker boxes exactly) and
 * the lint flag (lint renders skip video decoding: only the layout matters).
 */
import { createContext, useContext } from 'react'

import type { EpisodeState } from './state'

export type ImageSizes = Record<string, [number, number]>

export type EpisodeData = { state: EpisodeState; imageSizes: ImageSizes; lint: boolean }

export const EpisodeContext = createContext<EpisodeData | null>(null)

export function useEpisode(): EpisodeData {
  const data = useContext(EpisodeContext)
  if (!data) throw new Error('block rendered outside the EpisodeContext')
  return data
}

/** The measured size of a public-dir image; calculateMetadata guarantees every PhotoPlate image is measured. */
export function imageSize(sizes: ImageSizes, src: string): [number, number] {
  const size = sizes[src]
  if (!size) throw new Error(`image ${src} was not measured`)
  return size
}
```

**`video/src/media.ts`** (complete file):

```ts
/**
 * Measurements calculateMetadata takes in the browser before the first frame:
 * narration clip lengths (the music ducks under them) and image pixel sizes
 * (PhotoPlate places fractional marker boxes in image pixels). Both read the
 * files of the per-render public dir; a file that cannot be read fails the render.
 */
import { staticFile } from 'remotion'

import type { ImageSizes } from './context'

/** Length of an audio file in seconds, from its metadata. */
export function audioSeconds(src: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const el = document.createElement('audio')
    el.preload = 'metadata'
    el.onloadedmetadata = () => resolve(el.duration)
    el.onerror = () => reject(new Error(`cannot read audio metadata of ${src}`))
    el.src = staticFile(src)
  })
}

/** Natural pixel size of an image. */
function imagePixels(src: string): Promise<[number, number]> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve([img.naturalWidth, img.naturalHeight])
    img.onerror = () => reject(new Error(`cannot load image ${src}`))
    img.src = staticFile(src)
  })
}

export async function measureImages(srcs: readonly string[]): Promise<ImageSizes> {
  const unique = [...new Set(srcs)]
  const sizes = await Promise.all(unique.map(imagePixels))
  return Object.fromEntries(unique.map((src, i) => [src, sizes[i]]))
}
```

**`video/src/gpu.ts`** (complete file):

```ts
/**
 * The GPU proof of the render browser (spec 2026-09-26 section 4.11): the
 * WebGL renderer string of the Chrome that renders the frames. The
 * compositions' calculateMetadata puts it into their props, so every node
 * script reads it from selectComposition() in the same browser that will
 * render, and refuses anything but the NVIDIA (scripts/args.ts nvidiaProblem).
 */

/** UNMASKED_RENDERER_WEBGL of a fresh WebGL context, e.g. "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 ...)". */
export function webglRenderer(): string {
  const canvas = document.createElement('canvas')
  const gl = (canvas.getContext('webgl2') ?? canvas.getContext('webgl')) as WebGLRenderingContext | null
  if (!gl) throw new Error('the render browser has no WebGL context')
  const info = gl.getExtension('WEBGL_debug_renderer_info')
  if (!info) throw new Error('the render browser hides its WebGL renderer (no WEBGL_debug_renderer_info)')
  return String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL))
}
```

**`video/src/layout/LayoutBox.tsx`** (complete file):

```tsx
/**
 * LayoutBox registration. In lint mode every overlay and every text element
 * of a block measures itself after each frame's render (useLayoutEffect, so
 * before Remotion takes the screenshot) and stores its box in the Registry;
 * LayoutGuard then checks all boxes of the frame. Outside lint mode nothing
 * is measured.
 *
 * Lint mode measures only in the brand fonts. Remotion mounts the composition
 * without waiting for the fonts, and seeking a tab to the frame it already
 * shows (its first one) does not render again, so a measurement at mount
 * would judge that frame in a fallback font. The lint-mode LayoutProvider
 * therefore holds the render (delayRender) until brandFontsReady() resolves,
 * then renders once more with `fontsReady`, which makes every LayoutBox
 * measure and LayoutGuard report, and only then lets the frame go
 * (test/gpu/guard.gpu.ts proves it with fonts that arrive late).
 */
import React, { createContext, useContext, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useCurrentFrame, useCurrentScale, useDelayRender } from 'remotion'

import { brandFontsReady } from '../theme/fonts'
import type { Box, BoxKind } from './geometry'

export class Registry {
  readonly enabled: boolean
  readonly boxes = new Map<string, Box>()
  readonly overflow = new Set<string>()

  constructor(enabled: boolean) {
    this.enabled = enabled
  }

  set(box: Box, overflowing: boolean): void {
    if (!this.enabled) throw new Error(`LayoutBox ${box.id} was measured outside lint mode`)
    this.boxes.set(box.id, box)
    if (overflowing) this.overflow.add(box.id)
    else this.overflow.delete(box.id)
  }

  remove(id: string): void {
    this.boxes.delete(id)
    this.overflow.delete(id)
  }
}

/** The provider's registry and whether the brand fonts are in (always false outside lint mode). */
export type LayoutState = { registry: Registry; fontsReady: boolean }

const LayoutContext = createContext<LayoutState | null>(null)

/** Boxes are measured relative to this element (found with closest(), which works during layout effects). */
const ROOT_ATTR = 'data-layout-root'

export const LayoutProvider: React.FC<{ registry: Registry; children: ReactNode }> = ({ registry, children }) => {
  // The lint registry whose fonts are in, with the delayRender handle that held its render until then.
  const [ready, setReady] = useState<{ registry: Registry; handle: number } | null>(null)
  const { delayRender, continueRender, cancelRender } = useDelayRender()
  useLayoutEffect(() => {
    if (!registry.enabled) return
    const handle = delayRender('layout lint: waiting for the brand fonts before measuring')
    brandFontsReady().then(() => setReady({ registry, handle }), cancelRender)
  }, [registry, delayRender, cancelRender])
  // A parent's layout effects run after its children's: in the commit that made `ready`, every
  // LayoutBox has measured in the brand fonts and LayoutGuard has reported, so the frame may go.
  useLayoutEffect(() => {
    if (ready) continueRender(ready.handle)
  }, [ready, continueRender])
  const fontsReady = ready?.registry === registry
  const state = useMemo(() => ({ registry, fontsReady }), [registry, fontsReady])
  return (
    <LayoutContext.Provider value={state}>
      <div {...{ [ROOT_ATTR]: '' }} style={{ position: 'absolute', inset: 0 }}>
        {children}
      </div>
    </LayoutContext.Provider>
  )
}

export function useLayoutState(): LayoutState {
  const state = useContext(LayoutContext)
  if (!state) throw new Error('LayoutBox used outside LayoutProvider')
  return state
}

/** Measure the element behind the returned ref every frame and register it as `id`. */
export function useLayoutBox<T extends HTMLElement>(id: string, kind: BoxKind, allow: readonly string[] = []): React.RefObject<T> {
  const ref = useRef<T>(null)
  const { registry, fontsReady } = useLayoutState()
  const frame = useCurrentFrame()
  const scale = useCurrentScale()
  const allowKey = allow.join('|')
  useLayoutEffect(() => {
    if (!registry.enabled || !fontsReady) return
    const el = ref.current
    const root = el?.closest(`[${ROOT_ATTR}]`)
    if (!el || !root) throw new Error(`LayoutBox ${id}: element not mounted inside the LayoutProvider`)
    const r = el.getBoundingClientRect()
    const o = root.getBoundingClientRect()
    const rect = { x: (r.left - o.left) / scale, y: (r.top - o.top) / scale, w: r.width / scale, h: r.height / scale }
    // Only a box that clips (overflow hidden) can hide text; its content must fit.
    const clips = getComputedStyle(el).overflow === 'hidden'
    const overflowing = kind === 'text' && clips && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
    registry.set({ id, kind, rect, allow: allowKey ? allowKey.split('|') : [] }, overflowing)
    return () => registry.remove(id)
  }, [registry, fontsReady, id, kind, allowKey, frame, scale])
  return ref
}

export const LayoutBox: React.FC<{
  id: string
  kind: BoxKind
  allow?: readonly string[]
  style?: CSSProperties
  children?: ReactNode
}> = ({ id, kind, allow, style, children }) => {
  const ref = useLayoutBox<HTMLDivElement>(id, kind, allow)
  return (
    <div ref={ref} style={style}>
      {children}
    </div>
  )
}
```

**`video/src/layout/LayoutGuard.tsx`** (complete file):

```tsx
/**
 * Lint-mode reporter. Rendered as the LAST child of the LayoutProvider, so its
 * layout effect runs after every LayoutBox of the frame has registered (React
 * runs layout effects subtree by subtree in sibling order). It reports once
 * the brand fonts are in (LayoutBox.tsx) and then on every frame. Each
 * violation is one console.error line of JSON, which scripts/lint.ts collects
 * through onBrowserLog (test/gpu/guard.gpu.ts proves it in a real browser):
 *   {"type":"layout-violation","frame":123,"a":"captions","b":"b01:lt","reason":"overlap"}
 */
import React, { useLayoutEffect } from 'react'
import { useCurrentFrame } from 'remotion'

import { type Violation, findViolations } from './geometry'
import { useLayoutState } from './LayoutBox'

export const VIOLATION_TYPE = 'layout-violation'

/** The console line of one violation at `frame` (scripts/args.ts parseViolation reads it back). */
export function violationLine(frame: number, v: Violation): string {
  return JSON.stringify({ type: VIOLATION_TYPE, frame, a: v.a, b: v.b, reason: v.reason })
}

export const LayoutGuard: React.FC = () => {
  const frame = useCurrentFrame()
  const { registry, fontsReady } = useLayoutState()
  useLayoutEffect(() => {
    // Before the brand fonts are in, nothing is measured (LayoutBox.tsx) and there is nothing to report.
    if (!fontsReady) return
    for (const v of findViolations([...registry.boxes.values()], [...registry.overflow])) console.error(violationLine(frame, v))
  }, [frame, registry, fontsReady])
  if (!registry.enabled) throw new Error('LayoutGuard needs a lint-mode Registry (new Registry(true)): this one measures nothing')
  return null
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/guard.test.ts`
Expected: `Tests  4 passed (4)`

- [ ] **Step 5: Prove the gate in a real browser (workstation only)**

**`video/test/gpu/vitest.config.ts`** (complete file):

```ts
/**
 * The real-browser checks under test/gpu (`npm run test:gpu`, cwd video/). They
 * render in Remotion's Chrome on the RTX 3080 (spec 4.11), so they run on the
 * workstation only. The CI job lint-video runs `npm test`, whose config
 * (video/vitest.config.ts) collects only files named *.test.ts, never these
 * *.gpu.ts files.
 */
import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vitest/config'

export default defineConfig({
  root: fileURLToPath(new URL('../..', import.meta.url)),
  test: {
    include: ['test/gpu/**/*.gpu.ts'],
    environment: 'node',
    fileParallelism: false,
  },
})
```

**`video/test/gpu/guardFixture.tsx`** (complete file):

```tsx
/**
 * Remotion entry of the real-browser lint check (guard.gpu.ts): compositions
 * with planted layout violations, drawn through the real LayoutProvider,
 * LayoutBox and LayoutGuard in Remotion's Chrome.
 *
 * The brand font files arrive SLOW_FONTS_MS late (fetch is held back here, as
 * a slow disk or a cold cache would), so every composition mounts, and every
 * render tab reaches its first frame, while Orbitron is still missing and the
 * text is laid out in a fallback font. OVERFLOWING_TEASER takes two lines in
 * that fallback and three in Orbitron (measured 2026-09-27 in Remotion's
 * chrome-headless-shell), so a lint that measured before the fonts arrived
 * would pass it.
 */
import React, { useMemo } from 'react'
import type { CSSProperties } from 'react'
import { AbsoluteFill, type CalculateMetadataFunction, Composition, registerRoot, useCurrentFrame } from 'remotion'

import { webglRenderer } from '../../src/gpu'
import type { Rect } from '../../src/layout/geometry'
import { LayoutBox, LayoutProvider, Registry } from '../../src/layout/LayoutBox'
import { LayoutGuard } from '../../src/layout/LayoutGuard'
import { ZONES } from '../../src/layout/zones'
import { loadBrandFonts } from '../../src/theme/fonts'
import { body, heading } from '../../src/theme/type'

const SLOW_FONTS_MS = 2500

/** Four words: two lines in the fallback font, three in Orbitron 700 at 104 px (the teaser box holds two). */
const OVERFLOWING_TEASER = 'WHO ENGINEERED BAALBEK MONOLITHS?'
/** Two lines in both fonts: fits. */
const FITTING_TEASER = 'WHICH CIVILISATION QUARRIED THESE?'

const fetchNow = window.fetch.bind(window)
window.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
  String(input).includes('/fonts/') ? new Promise<void>((resolve) => setTimeout(resolve, SLOW_FONTS_MS)).then(() => fetchNow(input, init)) : fetchNow(input, init)
loadBrandFonts()

type LintProps = { lint: boolean; gpu: string }

const place = (r: Rect): CSSProperties => ({ position: 'absolute', left: r.x, top: r.y, width: r.w, height: r.h, overflow: 'hidden', ...body(30) })

/** The Thumbnail's teaser (plan D Task 18): TEASER_ZONE {96, 72, 1440, 380}, upper-case Orbitron 104 px, two lines at most. */
const Teaser: React.FC<{ id: string; text: string }> = ({ id, text }) => (
  <LayoutBox id={id} kind="text" style={{ position: 'absolute', left: 140, top: 96, width: 1368, height: 332, overflow: 'hidden', display: 'flex', alignItems: 'center', ...heading(104) }}>
    {text}
  </LayoutBox>
)

/**
 * Six frames. Every frame: the teaser overflows, `edge` leaves the title-safe
 * area, `lt` covers `captions`. From frame 3 on `drop` sits in the YouTube
 * controls. `fits` never breaks a rule. Rendered at scale 0.5, so a box
 * measured in device pixels instead of composition pixels would move `edge`
 * back inside the safe area and `drop` out of the controls.
 */
const Planted: React.FC<LintProps> = ({ lint }) => {
  const frame = useCurrentFrame()
  const registry = useMemo(() => new Registry(lint), [lint])
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <LayoutProvider registry={registry}>
        <Teaser id="teaser" text={OVERFLOWING_TEASER} />
        <LayoutBox id="captions" kind="text" style={place(ZONES.caption)}>
          A HOOK CAPTION
        </LayoutBox>
        <LayoutBox id="lt" kind="text" style={place({ x: 96, y: 780, w: 760, h: 96 })}>
          A LOWER THIRD
        </LayoutBox>
        <LayoutBox id="edge" kind="text" style={place({ x: 1800, y: 500, w: 100, h: 48 })}>
          EDGE
        </LayoutBox>
        <LayoutBox id="drop" kind="text" style={place({ x: 1200, y: frame < 3 ? 846 : 970, w: 300, h: 48 })}>
          DROP
        </LayoutBox>
        <LayoutBox id="fits" kind="text" style={place({ x: 1560, y: 300, w: 240, h: 64 })}>
          3 / 7
        </LayoutBox>
        {lint ? <LayoutGuard /> : null}
      </LayoutProvider>
    </AbsoluteFill>
  )
}

/**
 * One frame, built like the Thumbnail: the scene under a registry that never
 * measures (its overlapping pair must not be reported), the teaser under the
 * lint registry. `candidate` 1 carries the overflowing teaser, 2 the fitting one.
 */
const TeaserOnly: React.FC<LintProps & { candidate: number }> = ({ lint, candidate }) => {
  const scenes = useMemo(() => new Registry(false), [])
  const teaser = useMemo(() => new Registry(lint), [lint])
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <LayoutProvider registry={scenes}>
        <LayoutBox id="scene:a" kind="text" style={place(ZONES.caption)}>
          SCENE TEXT
        </LayoutBox>
        <LayoutBox id="scene:b" kind="text" style={place({ x: 96, y: 780, w: 760, h: 96 })}>
          SCENE TEXT
        </LayoutBox>
      </LayoutProvider>
      <LayoutProvider registry={teaser}>
        <Teaser id={`thumbnail${candidate}:teaser`} text={candidate === 1 ? OVERFLOWING_TEASER : FITTING_TEASER} />
        {lint ? <LayoutGuard /> : null}
      </LayoutProvider>
    </AbsoluteFill>
  )
}

const withGpu: CalculateMetadataFunction<LintProps> = async ({ props }) => ({ props: { ...props, gpu: webglRenderer() } })
const withGpuTeaser: CalculateMetadataFunction<LintProps & { candidate: number }> = async ({ props }) => ({ props: { ...props, gpu: webglRenderer() } })

const Root: React.FC = () => (
  <>
    <Composition id="Planted" component={Planted} defaultProps={{ lint: false, gpu: '' }} calculateMetadata={withGpu} durationInFrames={6} fps={60} width={1920} height={1080} />
    <Composition
      id="TeaserOnly"
      component={TeaserOnly}
      defaultProps={{ lint: false, gpu: '', candidate: 1 }}
      calculateMetadata={withGpuTeaser}
      durationInFrames={1}
      fps={60}
      width={1920}
      height={1080}
    />
  </>
)

registerRoot(Root)
```

**`video/test/gpu/guard.gpu.ts`** (complete file):

```ts
/**
 * The layout lint fires in a real browser (workstation only, not CI: it needs
 * the RTX 3080, spec 4.11). Run from video/: `npm run test:gpu`.
 *
 * guardFixture.tsx plants violations and delays the brand fonts; these tests
 * render it the way scripts/lint.ts does (renderFrames at scale 0.5, the
 * violations read from onBrowserLog) and require exactly the planted lines:
 * the overflow of a teaser that needs three lines in Orbitron (on every tab's
 * first frame too), text outside the title-safe area, text in the YouTube
 * controls, and an overlap; and nothing from a render outside lint mode or
 * from a registry that does not measure.
 */
import { cpSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { bundle } from '@remotion/bundler'
import { openBrowser, renderFrames, selectComposition } from '@remotion/renderer'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { SITE_PUBLIC_DIR } from '../../scripts/fontCoverage'
import type { Violation } from '../../src/layout/geometry'
import { VIOLATION_TYPE, violationLine } from '../../src/layout/LayoutGuard'
import { FONT_FILES } from '../../src/theme/fonts'

const NVIDIA = /^ANGLE \(NVIDIA, NVIDIA GeForce RTX 3080/
const SLOW = 180_000

let work = ''
let serveUrl = ''

beforeAll(async () => {
  work = mkdtempSync(path.join(os.tmpdir(), 'studio-guard-'))
  const publicDir = path.join(work, 'public')
  for (const file of FONT_FILES) {
    mkdirSync(path.dirname(path.join(publicDir, file)), { recursive: true })
    cpSync(path.join(SITE_PUBLIC_DIR, file), path.join(publicDir, file))
  }
  serveUrl = await bundle({ entryPoint: fileURLToPath(new URL('./guardFixture.tsx', import.meta.url)), publicDir, outDir: path.join(work, 'bundle') })
}, SLOW)

afterAll(() => {
  rmSync(work, { recursive: true, force: true })
})

/** Render every frame of `id` in a browser on the NVIDIA and return its renderer and its layout-violation console lines, sorted. */
async function lint(id: string, props: Record<string, unknown>, concurrency: number): Promise<{ gpu: string; lines: string[] }> {
  const browser = await openBrowser('chrome', { chromiumOptions: { gl: 'angle' } })
  try {
    const inputProps = { gpu: '', ...props }
    const composition = await selectComposition({ serveUrl, id, inputProps, puppeteerInstance: browser })
    const lines: string[] = []
    await renderFrames({
      composition,
      serveUrl,
      inputProps,
      puppeteerInstance: browser,
      imageFormat: 'jpeg',
      jpegQuality: 50,
      muted: true,
      outputDir: null,
      onFrameBuffer: () => undefined,
      onStart: () => undefined,
      onFrameUpdate: () => undefined,
      scale: 0.5,
      concurrency,
      timeoutInMilliseconds: 60_000,
      logLevel: 'error',
      onBrowserLog: (log) => {
        if (log.text.startsWith(`{"type":"${VIOLATION_TYPE}"`)) lines.push(log.text)
      },
    })
    return { gpu: String(composition.props.gpu), lines: lines.sort() }
  } finally {
    await browser.close({ silent: true })
  }
}

const expected = (entries: [number, Violation][]) => entries.map(([frame, v]) => violationLine(frame, v)).sort()

describe('LayoutGuard in a real browser (fonts arriving after the first frame)', () => {
  it('reports exactly the planted violations of every frame, each tab`s first frame included', async () => {
    const { gpu, lines } = await lint('Planted', { lint: true }, 2)
    expect(gpu).toMatch(NVIDIA)
    const want: [number, Violation][] = []
    for (let frame = 0; frame < 6; frame++) {
      want.push([frame, { a: 'teaser', b: null, reason: 'overflow' }])
      want.push([frame, { a: 'edge', b: null, reason: 'outside-safe' }])
      want.push([frame, { a: 'captions', b: 'lt', reason: 'overlap' }])
      if (frame >= 3) want.push([frame, { a: 'drop', b: null, reason: 'controls' }])
    }
    expect(lines).toEqual(expected(want))
  }, SLOW)

  it('measures nothing outside lint mode', async () => {
    const { gpu, lines } = await lint('Planted', { lint: false }, 2)
    expect(gpu).toMatch(NVIDIA)
    expect(lines).toEqual([])
  }, SLOW)

  it('checks a one-frame thumbnail teaser, and only the teaser', async () => {
    const overflowing = await lint('TeaserOnly', { lint: true, candidate: 1 }, 1)
    expect(overflowing.gpu).toMatch(NVIDIA)
    expect(overflowing.lines).toEqual(expected([[0, { a: 'thumbnail1:teaser', b: null, reason: 'overflow' }]]))
    const fitting = await lint('TeaserOnly', { lint: true, candidate: 2 }, 1)
    expect(fitting.lines).toEqual([])
  }, SLOW)
})
```

Run: `cd video && npx tsc --noEmit && npm run test:gpu`
Expected: no tsc output, then `Test Files  1 passed (1)` and `Tests  3 passed (3)` in about 35 s (measured 2026-09-27 on the RTX 3080). The violation lines of the lint-mode renders also appear on stderr, each after `Tab N, src/layout/LayoutGuard.tsx:<line>`. Without the font hold the check fails. Measured 2026-09-27 with `LayoutBox.tsx`, `LayoutGuard.tsx` and `fonts.ts` as Task 11 first committed them (2d44956: the provider only passes the registry on, and nothing waits for `fontsReady`): `Tests  2 failed | 1 passed (3)`. The first test receives 19 lines instead of 21, without the teaser overflows of the two tabs' first frames, and the one-frame teaser gives `[]`. On any other GPU every test fails on the renderer string.

- [ ] **Step 6: Commit**

```bash
git add video/src/context.ts video/src/media.ts video/src/gpu.ts video/src/layout/LayoutBox.tsx video/src/layout/LayoutGuard.tsx video/test/guard.test.ts video/test/gpu/vitest.config.ts video/test/gpu/guardFixture.tsx video/test/gpu/guard.gpu.ts
git commit -m "Register layout boxes in lint mode once the brand fonts are in, report each violation as a JSON console line, and prove it in Remotion's Chrome on the NVIDIA" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 12: Block types, clip rules, primitives and the overlays

**Files:**
- Create: `video/src/blocks/types.ts`, `video/src/blocks/clips.ts`, `video/src/blocks/Panel.tsx`, `video/src/blocks/Stamp.tsx`, `video/src/blocks/LowerThird.tsx`, `video/src/blocks/CreditLine.tsx`, `video/src/blocks/ChapterTag.tsx`, `video/src/blocks/Ticker.tsx`, `video/src/blocks/HookCaptions.tsx`, `video/src/blocks/Footage.tsx`, `video/src/blocks/ImageLayer.tsx`
- Test: `video/test/clips.test.ts`

The pieces the scene blocks share. `Footage` plays a captured clip through `@remotion/media` `<Video>` with `disallowFallbackToOffthreadVideo` (a clip it cannot decode fails the render; in lint mode no clip is decoded). `ImageLayer` draws an image with its markers, pins and distance lines in one transformed layer and places the labels in screen space through the same view (owner rule: markers move with their image). The overlays follow the owner's picture rules: no title card (the chapter tag skips 0:00), the evidence counter without series branding, captions only where the timeline has them (the hook), credits drawn in-frame above the player controls. `CreditLine` takes an optional `zone` (default `ZONES.credit`): the Thumbnail (Task 18) draws its scene's credit line bottom left, clear of YouTube's duration badge.

- [ ] **Step 1: Write the failing test**

**`video/test/clips.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { chapterTagIndex } from '../src/blocks/ChapterTag'
import { clipProblems, clipTime, trimFrames } from '../src/blocks/clips'
import type { Capture } from '../src/blocks/types'

const clip: Capture = {
  id: 'pf1',
  kind: 'platform',
  src: 'captures/pf1.mp4',
  fps: 60,
  duration_s: 4,
  width: 2880,
  height: 1620,
  events: [],
  credits: [],
}

describe('clip rules', () => {
  it('accepts a clip that covers its scene from the start offset', () => {
    expect(clipProblems(clip, 0.5, { fps: 60, durationInFrames: 210 })).toEqual([])
  })
  it('refuses a clip that would end before its scene (black frames)', () => {
    expect(clipProblems(clip, 1, { fps: 60, durationInFrames: 240 })).toEqual([
      'capture pf1 is 4 s long; the scene needs 5.000 s from 1 s (record a longer take or shorten the beat)',
    ])
  })
  it('refuses a still where a clip belongs', () => {
    expect(clipProblems({ ...clip, fps: null, duration_s: null }, 0, { fps: 60, durationInFrames: 60 })).toEqual(['capture pf1 is a still, not a clip'])
  })
  it('converts between clip seconds and scene frames', () => {
    expect(trimFrames(0.5, 60)).toBe(30)
    expect(clipTime(0.5, 90, 60)).toBe(2)
  })
})

describe('chapter tag (owner rule: no title card)', () => {
  const chapters = [
    { title: 'The stone', frame: 0 },
    { title: 'On the globe', frame: 600 },
  ]
  it('shows no tag during the first chapter and the second chapter tag for three seconds', () => {
    for (let frame = 0; frame < 600; frame++) expect(chapterTagIndex(chapters, frame, 60)).toBeNull()
    for (let frame = 600; frame < 780; frame++) expect(chapterTagIndex(chapters, frame, 60)).toBe(1)
    expect(chapterTagIndex(chapters, 780, 60)).toBeNull()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/clips.test.ts`
Expected: FAIL with `Cannot find module '../src/blocks/ChapterTag'`.

- [ ] **Step 3: Implement**

**`video/src/blocks/types.ts`** (complete file):

```ts
/**
 * What every scene block receives, and the resolved case-file and capture
 * shapes of its props (plan C contract C6; the schemas are in schemas.ts).
 */
import type { SceneCue } from '../cues'
import type { Rect } from '../layout/geometry'
import type { ClaimStatus } from '../theme/colors'
import type { IconName } from './icons'

export type BlockProps<P> = {
  props: P
  /** The scene's cues with scene-relative frames. */
  cues: readonly SceneCue[]
  durationInFrames: number
  /** Prefix of LayoutBox ids, so lint reports name the scene. */
  sceneId: string
  /** Absolute frame of the scene start: global cue state (state.ts) is keyed by absolute frames. */
  sceneFrom: number
  /** Where the block's graphics go: the stage, shorter in scenes with hook captions. */
  stage: Rect
}

export type Label = { title: string; subtitle?: string }

export type Marker = { id: string; box: [number, number, number, number]; label: string }
export type Media = {
  id: string
  src: string
  license: string
  attribution: string
  source_url: string
  depicts: string
  markers: Marker[]
}

export type EvidenceKind = 'fact' | 'quote' | 'quantity' | 'date' | 'image' | 'place'
export type Evidence = {
  id: string
  claim_id: string
  kind: EvidenceKind
  statement: string
  source: { url: string; title: string; tier: number; license: string; quote: string; locator: string }
  paper_anchor: string | null
}

export type Claim = { id: string; label: string; by: string; icon: IconName; status: ClaimStatus }

export type CaptureEvent = {
  t: number
  name: string
  x?: number
  y?: number
  box?: [number, number, number, number]
  target?: string
  label?: string
  url?: string
  title?: string
  lat?: number
  lng?: number
  /** Globe place events: [x, y] in every capture frame from the event on, null while hidden. */
  track?: ([number, number] | null)[]
}
export type Capture = {
  id: string
  kind: 'platform' | 'globe' | 'source' | 'mapbox_topdown'
  src: string
  fps: number | null
  duration_s: number | null
  width: number
  height: number
  events: CaptureEvent[]
  credits: string[]
}

/** What a block's check() gets besides its props. */
export type CheckContext = { fps: number; durationInFrames: number }
```

**`video/src/blocks/clips.ts`** (complete file):

```ts
/**
 * Shared rules of the clip blocks (PlatformClip, GlobeShot, MapboxFlyover):
 * a clip must cover its whole scene (a clip that ends early would leave black
 * frames, which the render audit refuses), and the capture clock <-> scene
 * frame arithmetic.
 */
import type { Capture, CheckContext } from './types'

/** Every way `clip`, started `startS` seconds in, fails to fill a scene of ctx.durationInFrames. */
export function clipProblems(clip: Capture, startS: number, ctx: CheckContext): string[] {
  if (clip.fps === null || clip.duration_s === null) return [`capture ${clip.id} is a still, not a clip`]
  const need = startS + ctx.durationInFrames / ctx.fps
  if (need > clip.duration_s + 1e-6) {
    return [`capture ${clip.id} is ${clip.duration_s} s long; the scene needs ${need.toFixed(3)} s from ${startS} s (record a longer take or shorten the beat)`]
  }
  return []
}

/** trimBefore of the clip in composition frames. */
export function trimFrames(startS: number, fps: number): number {
  return Math.round(startS * fps)
}

/** Seconds on the capture clock at scene frame `frame`. */
export function clipTime(startS: number, frame: number, fps: number): number {
  return startS + frame / fps
}
```

**`video/src/blocks/Panel.tsx`** (complete file):

```tsx
/**
 * NERV panel frame for the card blocks: dark glass, an outline traced in
 * (border-trace), corner brackets and one light sweep across after the panel
 * has opened (crt-open).
 */
import React from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useCurrentFrame } from 'remotion'

import type { Rect } from '../layout/geometry'
import { borderTrace, crtOpen, sweep } from '../motion'
import { colors } from '../theme/colors'

const BRACKET = 22

export const Panel: React.FC<{ rect: Rect; start?: number; accent?: string; children?: ReactNode }> = ({ rect, start = 0, accent = colors.green, children }) => {
  const frame = useCurrentFrame()
  const perimeter = 2 * (rect.w + rect.h)
  const line = `3px solid ${accent}`
  const corner = (pos: CSSProperties) => <div style={{ position: 'absolute', width: BRACKET, height: BRACKET, ...pos }} />
  const pass = sweep(frame, start + 24, 40)
  return (
    <div style={{ position: 'absolute', left: rect.x, top: rect.y, width: rect.w, height: rect.h, transformOrigin: 'center', ...crtOpen(frame, start) }}>
      <div style={{ position: 'absolute', inset: 0, background: colors.bgPanel }} />
      <svg width={rect.w} height={rect.h} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
        <rect
          x={0.5}
          y={0.5}
          width={rect.w - 1}
          height={rect.h - 1}
          fill="none"
          stroke={accent}
          strokeOpacity={0.55}
          strokeWidth={1}
          strokeDasharray={perimeter}
          strokeDashoffset={borderTrace(frame, start + 4, 24, perimeter)}
        />
      </svg>
      {pass > 0 && pass < 1 ? (
        <div style={{ position: 'absolute', top: 0, bottom: 0, left: pass * rect.w, width: 3, background: accent, opacity: 0.35 * Math.sin(pass * Math.PI) }} />
      ) : null}
      {corner({ left: -2, top: -2, borderLeft: line, borderTop: line })}
      {corner({ right: -2, top: -2, borderRight: line, borderTop: line })}
      {corner({ left: -2, bottom: -2, borderLeft: line, borderBottom: line })}
      {corner({ right: -2, bottom: -2, borderRight: line, borderBottom: line })}
      <div style={{ position: 'absolute', inset: 0 }}>{children}</div>
    </div>
  )
}
```

**`video/src/blocks/Stamp.tsx`** (complete file):

```tsx
/**
 * A verdict stamp that slams in at `start` (VERIFIED, WEAKENED, REFUTED ...).
 * The measured LayoutBox is the transformed element itself, so the lint sees
 * the rotated, scaled stamp exactly as drawn.
 */
import React from 'react'
import type { CSSProperties } from 'react'
import { useCurrentFrame, useVideoConfig } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import { stampSlam } from '../motion'
import { heading } from '../theme/type'

export const Stamp: React.FC<{ id: string; text: string; color: string; start: number; size?: number; style?: CSSProperties }> = ({
  id,
  text,
  color,
  start,
  size = 34,
  style,
}) => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  if (frame < start) return null
  return (
    <LayoutBox
      id={id}
      kind="text"
      style={{
        position: 'absolute',
        ...heading(size, color),
        padding: '6px 18px',
        border: `4px solid ${color}`,
        borderRadius: 6,
        whiteSpace: 'nowrap',
        background: 'rgba(10, 14, 20, 0.6)',
        ...style,
        ...stampSlam(frame, start, fps),
      }}
    >
      {text}
    </LayoutBox>
  )
}
```

**`video/src/blocks/LowerThird.tsx`** (complete file):

```tsx
/**
 * Place label over footage, bottom left (zone lowerThird). It sits on its own
 * dark glass so it reads over any capture, including the site's busy UI.
 */
import React from 'react'
import { useCurrentFrame } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import { ZONES } from '../layout/zones'
import { bootIn, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, heading } from '../theme/type'
import type { Label } from './types'

export const LowerThird: React.FC<{ id: string; label: Label; start?: number }> = ({ id, label, start = 12 }) => {
  const frame = useCurrentFrame()
  const z = ZONES.lowerThird
  const bar = progress(frame, start, 14)
  return (
    <div style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, ...bootIn(frame, start) }}>
      <div style={{ position: 'absolute', inset: 0, background: colors.bgPanel }} />
      <div style={{ position: 'absolute', left: 0, top: 0, width: 6, height: z.h * bar, background: colors.green }} />
      <LayoutBox id={id} kind="text" style={{ position: 'absolute', left: 26, top: 8, width: z.w - 44, height: z.h - 16, overflow: 'hidden' }}>
        <div style={{ ...heading(38), whiteSpace: 'nowrap' }}>{label.title}</div>
        {label.subtitle ? <div style={{ ...body(24, colors.crt300), whiteSpace: 'nowrap' }}>{label.subtitle}</div> : null}
      </LayoutBox>
    </div>
  )
}
```

**`video/src/blocks/CreditLine.tsx`** (complete file):

```tsx
/**
 * The scene's in-frame credit (timeline.credits: photo licences, source pages,
 * Mapbox/OpenStreetMap/Maxar for map content), merged into one line. Visible for
 * the whole scene, by default right aligned in the credit zone above the YouTube
 * controls. `zone` puts it elsewhere (the Thumbnail's THUMBNAIL_CREDIT_ZONE,
 * bottom left); the line is aligned to the frame edge its zone is nearer to.
 */
import React from 'react'

import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { FRAME, ZONES } from '../layout/zones'
import { body, overFootage } from '../theme/type'

export const CreditLine: React.FC<{ id: string; text: string; zone?: Rect }> = ({ id, text, zone: z = ZONES.credit }) => {
  return (
    <LayoutBox
      id={id}
      kind="text"
      style={{
        position: 'absolute',
        left: z.x,
        top: z.y,
        width: z.w,
        height: z.h,
        overflow: 'hidden',
        textAlign: z.x + z.w / 2 > FRAME.w / 2 ? 'right' : 'left',
        whiteSpace: 'nowrap',
        ...body(18, 'rgba(255, 255, 255, 0.85)'),
        lineHeight: `${z.h}px`,
        ...overFootage,
      }}
    >
      {text}
    </LayoutBox>
  )
}
```

**`video/src/blocks/ChapterTag.tsx`** (complete file):

```tsx
/**
 * Chapter tag (top left) for three seconds after each chapter start, so the
 * structure reads without narration. The chapter at frame 0 (the hook) gets no
 * tag: the video opens straight into the hook, never on a title card.
 */
import React from 'react'
import { useCurrentFrame, useVideoConfig } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import { ZONES } from '../layout/zones'
import { bootIn, typeOn } from '../motion'
import { colors } from '../theme/colors'
import { hud, overFootage } from '../theme/type'
import type { Chapter } from '../timeline'

/** Index of the chapter whose tag shows at `frame` (three seconds from its start), null for none; never the first chapter. */
export function chapterTagIndex(chapters: readonly Chapter[], frame: number, fps: number): number | null {
  const index = chapters.findIndex((c, i) => i > 0 && frame >= c.frame && frame < c.frame + 3 * fps)
  return index < 0 ? null : index
}

export const ChapterTag: React.FC<{ chapters: readonly Chapter[] }> = ({ chapters }) => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const index = chapterTagIndex(chapters, frame, fps)
  if (index === null) return null
  const chapter = chapters[index]
  const z = ZONES.chapter
  return (
    <LayoutBox id="chapter" kind="text" style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, overflow: 'hidden', whiteSpace: 'nowrap', ...overFootage, ...bootIn(frame, chapter.frame) }}>
      <span style={hud(22, colors.crt300)}>{`CH ${String(index).padStart(2, '0')} // `}</span>
      <span style={hud(22, colors.green)}>{typeOn(chapter.title, frame, chapter.frame + 4, 1)}</span>
    </LayoutBox>
  )
}
```

**`video/src/blocks/Ticker.tsx`** (complete file):

```tsx
/**
 * Evidence counter (top right): how many sourced evidence items the episode
 * has shown so far. Hidden until the first item; the number rolls on change.
 * No series branding (owner rule).
 */
import React from 'react'
import { useCurrentFrame } from 'remotion'

import { tickerAt } from '../captions'
import { LayoutBox } from '../layout/LayoutBox'
import { ZONES } from '../layout/zones'
import { bootIn, digitRoll } from '../motion'
import { colors } from '../theme/colors'
import { hud, overFootage } from '../theme/type'
import type { TickerStep } from '../timeline'

export const Ticker: React.FC<{ steps: readonly TickerStep[] }> = ({ steps }) => {
  const frame = useCurrentFrame()
  const { n, previous, since } = tickerAt(steps, frame)
  if (n === 0) return null
  const shown = digitRoll(previous, n, frame, since, 18)
  const first = steps.find((s) => s.n > 0)?.frame ?? 0
  const z = ZONES.ticker
  return (
    <LayoutBox
      id="ticker"
      kind="text"
      style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 14, ...overFootage, ...bootIn(frame, first) }}
    >
      <span style={hud(20, colors.crt300)}>Evidence</span>
      <span style={{ ...hud(44, colors.green), letterSpacing: '0.04em' }}>{String(shown).padStart(2, '0')}</span>
    </LayoutBox>
  )
}
```

**`video/src/blocks/HookCaptions.tsx`** (complete file):

```tsx
/**
 * Burned-in captions, for the hook only (owner rule: afterwards viewers use
 * YouTube's captions from the exact SRT). timeline.captions is empty after the
 * hook; the spoken word is green, the rest of the line white. A line is one row
 * of at most HOOK_LINE_MAX_CHARS characters (captions.ts), which fits the zone for
 * ordinary words; lint.ts reports a wider run of capitals as an overflow.
 */
import React, { useMemo } from 'react'
import { useCurrentFrame } from 'remotion'

import { captionLines, lineAt } from '../captions'
import { LayoutBox } from '../layout/LayoutBox'
import { ZONES } from '../layout/zones'
import { colors } from '../theme/colors'
import { heading, overFootage } from '../theme/type'
import type { Caption } from '../timeline'

export const HookCaptions: React.FC<{ captions: readonly Caption[] }> = ({ captions }) => {
  const frame = useCurrentFrame()
  const lines = useMemo(() => captionLines(captions), [captions])
  const line = lineAt(lines, frame)
  if (!line) return null
  const z = ZONES.caption
  return (
    <LayoutBox
      id="captions"
      kind="text"
      style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <div style={{ ...heading(64), textAlign: 'center', whiteSpace: 'nowrap', ...overFootage }}>
        {line.words.map((w, i) => (
          <span key={`${w.from}-${i}`} style={{ color: frame >= w.from && frame < w.to ? colors.green : colors.white }}>
            {i > 0 ? ' ' : ''}
            {w.text}
          </span>
        ))}
      </div>
    </LayoutBox>
  )
}
```

**`video/src/blocks/Footage.tsx`** (complete file):

```tsx
/**
 * A captured clip (pipeline/studio/capture: HEVC from hevc_nvenc on GPU 0, constant 60 fps) through
 * @remotion/media <Video>, which extracts exact frames. There is no fallback
 * to OffthreadVideo: a clip Mediabunny cannot decode fails the render. In lint
 * mode the clip is not decoded at all (the lint checks layout only), a flat
 * panel of the clip's size stands in.
 */
import React from 'react'
import type { CSSProperties } from 'react'
import { Video } from '@remotion/media'
import { staticFile } from 'remotion'

import { useEpisode } from '../context'
import { colors } from '../theme/colors'

export const Footage: React.FC<{ src: string; trimBefore: number; style: CSSProperties }> = ({ src, trimBefore, style }) => {
  const { lint } = useEpisode()
  if (lint) return <div style={{ ...style, background: colors.bgPanel }} />
  return <Video src={staticFile(src)} trimBefore={trimBefore} muted objectFit="fill" disallowFallbackToOffthreadVideo style={style} />
}
```

**`video/src/blocks/ImageLayer.tsx`** (complete file):

```tsx
/**
 * An image in one transformed layer together with its markers (PhotoPlate) or
 * pins and distance lines (MapboxTopdown). Ring, pin and line geometry live
 * inside the layer in image pixels, so they move with the image exactly (owner
 * rule); stroke widths are divided by the view scale to stay constant on
 * screen. Labels are drawn in screen space at the transformed position and
 * registered for the overlap lint.
 */
import React from 'react'
import { Img, staticFile, useCurrentFrame } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import type { ImageBox, View } from '../layout/transform'
import { rectToScreen, toScreen } from '../layout/transform'
import { ZONES } from '../layout/zones'
import { bootIn, progress, ringPulse, typeOn } from '../motion'
import { colors } from '../theme/colors'
import { hud } from '../theme/type'

export type LayerMark = { id: string; box: ImageBox; label: string; appear: number; focused: boolean; shape: 'ring' | 'pin' }
export type LayerLine = { id: string; from: { x: number; y: number }; to: { x: number; y: number }; text: string; appear: number }

const LABEL_H = 44
const LABEL_GAP = 14
const LINE_DRAW_FRAMES = 24

export const ImageLayer: React.FC<{
  sceneId: string
  src: string
  width: number
  height: number
  view: View
  marks: readonly LayerMark[]
  lines?: readonly LayerLine[]
}> = ({ sceneId, src, width, height, view, marks, lines = [] }) => {
  const frame = useCurrentFrame()
  const stroke = 3 / view.scale
  const shown = marks.filter((m) => frame >= m.appear)
  return (
    <>
      <div style={{ position: 'absolute', left: 0, top: 0, width, height, transformOrigin: '0 0', transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})` }}>
        <Img src={staticFile(src)} style={{ position: 'absolute', left: 0, top: 0, width, height }} />
        <svg width={width} height={height} style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible' }}>
          {lines
            .filter((l) => frame >= l.appear)
            .map((l) => {
              const len = Math.hypot(l.to.x - l.from.x, l.to.y - l.from.y)
              const drawn = progress(frame, l.appear, LINE_DRAW_FRAMES)
              return <line key={l.id} x1={l.from.x} y1={l.from.y} x2={l.to.x} y2={l.to.y} stroke={colors.amber} strokeWidth={stroke} strokeDasharray={`${len * drawn} ${len}`} />
            })}
          {shown.map((m) => {
            const [x, y, w, h] = m.box
            const pulse = ringPulse(frame, m.appear)
            const cx = x + w / 2
            const cy = y + h / 2
            const color = m.focused ? colors.amber : colors.green
            if (m.shape === 'pin') {
              const r = 10 / view.scale
              return (
                <g key={m.id}>
                  <circle cx={cx} cy={cy} r={r * pulse.scale * 2} fill="none" stroke={color} strokeWidth={stroke} opacity={pulse.opacity} />
                  <circle cx={cx} cy={cy} r={r} fill={color} stroke={colors.bg} strokeWidth={stroke * 0.7} />
                </g>
              )
            }
            return (
              <g key={m.id}>
                <rect x={x} y={y} width={w} height={h} fill="none" stroke={color} strokeWidth={stroke} rx={6 / view.scale} />
                <ellipse cx={cx} cy={cy} rx={(w / 2) * pulse.scale * 1.25} ry={(h / 2) * pulse.scale * 1.25} fill="none" stroke={color} strokeWidth={stroke} opacity={pulse.opacity} />
              </g>
            )
          })}
        </svg>
      </div>
      {shown.map((m) => {
        const r = rectToScreen(view, m.box)
        const ringId = `${sceneId}:mark:${m.id}`
        const labelId = `${sceneId}:label:${m.id}`
        const above = r.y - LABEL_GAP - LABEL_H >= ZONES.stage.y
        const top = above ? r.y - LABEL_GAP - LABEL_H : r.y + r.h + LABEL_GAP
        const color = m.focused ? colors.amber : colors.green
        return (
          <React.Fragment key={m.id}>
            <LayoutBox id={ringId} kind="mark" allow={[labelId]} style={{ position: 'absolute', left: r.x, top: r.y, width: r.w, height: r.h }} />
            <div style={{ position: 'absolute', left: r.x + r.w / 2, top, ...bootIn(frame, m.appear + 6, 12, 'translateX(-50%)') }}>
              <LayoutBox
                id={labelId}
                kind="text"
                allow={[ringId]}
                style={{ ...hud(26, colors.bg), background: color, padding: '7px 16px', whiteSpace: 'nowrap', height: LABEL_H, boxSizing: 'border-box' }}
              >
                {typeOn(m.label, frame, m.appear + 6, 1.2)}
              </LayoutBox>
            </div>
          </React.Fragment>
        )
      })}
      {lines
        .filter((l) => frame >= l.appear + LINE_DRAW_FRAMES)
        .map((l) => {
          const a = toScreen(view, l.from.x, l.from.y)
          const b = toScreen(view, l.to.x, l.to.y)
          return (
            <div key={l.id} style={{ position: 'absolute', left: (a.x + b.x) / 2, top: (a.y + b.y) / 2 - LABEL_H - 10, ...bootIn(frame, l.appear + LINE_DRAW_FRAMES, 12, 'translateX(-50%)') }}>
              <LayoutBox id={`${sceneId}:line:${l.id}`} kind="text" style={{ ...hud(26, colors.bg), background: colors.amber, padding: '7px 16px', whiteSpace: 'nowrap', height: LABEL_H, boxSizing: 'border-box' }}>
                {l.text}
              </LayoutBox>
            </div>
          )
        })}
    </>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/clips.test.ts && npx tsc --noEmit`
Expected: `Tests  5 passed (5)`, then no tsc output.

- [ ] **Step 5: Commit**

```bash
git add video/src/blocks/types.ts video/src/blocks/clips.ts video/src/blocks/Panel.tsx video/src/blocks/Stamp.tsx video/src/blocks/LowerThird.tsx video/src/blocks/CreditLine.tsx video/src/blocks/ChapterTag.tsx video/src/blocks/Ticker.tsx video/src/blocks/HookCaptions.tsx video/src/blocks/Footage.tsx video/src/blocks/ImageLayer.tsx video/test/clips.test.ts
git commit -m "Add the shared block pieces: clip rules, panels, stamps, credits, chapter tag, evidence counter and hook captions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 13: PhotoPlate and MapboxTopdown

**Files:**
- Create: `video/src/blocks/PhotoPlate.tsx`, `video/src/blocks/MapboxTopdown.tsx`
- Test: `video/test/blocks-image.test.ts`

PhotoPlate shows a checked photo full bleed with a Ken Burns camera and the case file's crop-checked marker boxes; a `highlight` cue flies the camera onto a marker. It has no measuring line: photos are oblique (owner rule; ScaleDrawing makes the comparison). MapboxTopdown shows an exact top-down satellite frame; being orthographic, it may carry distance lines, whose text is computed from the pins' coordinates.

- [ ] **Step 1: Write the failing test**

**`video/test/blocks-image.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { checkMapboxTopdown, pinsOf } from '../src/blocks/MapboxTopdown'
import { checkPhotoPlate, plateCamera } from '../src/blocks/PhotoPlate'
import type { Capture, Media } from '../src/blocks/types'

const image: Media = {
  id: 'm1',
  src: 'media/stone_person.jpg',
  license: 'CC BY-SA 4.0',
  attribution: 'Jane Doe',
  source_url: 'https://commons.wikimedia.org/wiki/File:Stone.jpg',
  depicts: 'the Stone of the Pregnant Woman with one person for scale',
  markers: [{ id: 'mk1', box: [0.625, 0.583, 0.075, 0.2], label: '1 PERSON' }],
}

const topdown: Capture = {
  id: 'td1',
  kind: 'mapbox_topdown',
  src: 'captures/td1.jpg',
  fps: null,
  duration_s: null,
  width: 2560,
  height: 1440,
  events: [
    { t: 0, name: 'pin', target: 'p2', label: 'Quarry', x: 1065, y: 1355, lat: 33.99917, lng: 36.20028 },
    { t: 0, name: 'pin', target: 'p1', label: 'Temple of Jupiter', x: 1496, y: 77, lat: 34.00667, lng: 36.20333 },
  ],
  credits: ['© Mapbox © Maxar'],
}

describe('PhotoPlate', () => {
  it('pushes in slowly, then flies onto the marker after its highlight cue', () => {
    const cues = [{ frame: 60, do: 'highlight' as const, target: 'mk1' }]
    expect(plateCamera(image, [1600, 1200], 'in', cues, 30, 300, 1920, 1080).zoom).toBeLessThan(1.02)
    const after = plateCamera(image, [1600, 1200], 'in', cues, 200, 300, 1920, 1080)
    expect(after.cx).toBeCloseTo(1060)
    expect(after.cy).toBeCloseTo(819.6, 0)
    expect(after.zoom).toBeGreaterThan(1.5)
  })
  it('refuses a marker box outside its image', () => {
    expect(checkPhotoPlate({ image: { ...image, markers: [{ id: 'mk1', box: [0.9, 0.5, 0.2, 0.1], label: '1 PERSON' }] } })).toEqual([
      'marker mk1 box [0.9,0.5,0.2,0.1] is not a box inside the image (fractions 0..1)',
    ])
    expect(checkPhotoPlate({ image })).toEqual([])
  })
})

describe('MapboxTopdown', () => {
  it('reads its pins from the capture events', () => {
    expect(pinsOf(topdown)).toEqual([
      { id: 'p2', label: 'Quarry', x: 1065, y: 1355, lat: 33.99917, lng: 36.20028 },
      { id: 'p1', label: 'Temple of Jupiter', x: 1496, y: 77, lat: 34.00667, lng: 36.20333 },
    ])
  })
  it('refuses a frame without pins, pins off the image and lines between unknown pins', () => {
    expect(checkMapboxTopdown({ map: topdown, lines: [{ from: 'p2', to: 'p1' }] })).toEqual([])
    expect(checkMapboxTopdown({ map: { ...topdown, events: [] } })).toEqual(['capture td1 has no pin events'])
    const off = { ...topdown, events: [{ ...topdown.events[0], x: 3000 }] }
    expect(checkMapboxTopdown({ map: off })).toEqual(['pin p2 lies outside the 2560x1440 image'])
    expect(checkMapboxTopdown({ map: topdown, lines: [{ from: 'p2', to: 'p9' }] })).toEqual(['line p2 -> p9 must join two different pins of the capture'])
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/blocks-image.test.ts`
Expected: FAIL with `Cannot find module '../src/blocks/MapboxTopdown'`.

- [ ] **Step 3: Implement**

**`video/src/blocks/PhotoPlate.tsx`** (complete file):

```tsx
/**
 * PhotoPlate: a checked photo, full bleed, with a Ken Burns camera and the
 * case file's markers in the same transformed layer (ImageLayer), so a marker
 * stays on its object while the image moves (owner rule). Markers are the
 * case file's crop-checked boxes, given as fractions of the image; the image's
 * pixel size is measured by calculateMetadata. Cues:
 *   show <marker>       the marker appears (without a show cue: from the start)
 *   hide <marker>       it leaves
 *   highlight <marker>  the camera flies onto it (36 frames) and holds; it turns amber
 * There is deliberately no measuring line: photos are oblique, so lengths
 * drawn on them would lie (owner rule); ScaleDrawing makes the comparison.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { type SceneCue, firstCue, visibleAt } from '../cues'
import { imageSize, useEpisode } from '../context'
import { LayoutBox } from '../layout/LayoutBox'
import { type Camera, type KenBurns, blendCamera, cameraAt, focusCamera, fractionBox, kenBurnsCamera, viewFor } from '../layout/transform'
import { bootIn, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, overFootage } from '../theme/type'
import { ImageLayer } from './ImageLayer'
import { LowerThird } from './LowerThird'
import type { BlockProps, Label, Media } from './types'

export type PhotoPlateProps = { image: Media; kenBurns?: KenBurns; label?: Label; caption?: string }

const FOCUS_FRAMES = 36

/** Camera at a scene frame: the Ken Burns path, overridden from the latest highlight cue on. */
export function plateCamera(
  image: Pick<Media, 'markers'>,
  size: [number, number],
  kenBurns: KenBurns,
  cues: readonly SceneCue[],
  frame: number,
  durationInFrames: number,
  fw: number,
  fh: number,
): Camera {
  const [iw, ih] = size
  const keys = kenBurnsCamera(iw, ih, kenBurns)
  const t = (f: number) => (durationInFrames > 1 ? f / (durationInFrames - 1) : 0)
  const focus = cues.filter((c) => c.do === 'highlight' && c.frame <= frame).sort((a, b) => a.frame - b.frame).pop()
  if (!focus) return cameraAt(keys, t(frame))
  const marker = image.markers.find((m) => m.id === focus.target)
  if (!marker) throw new Error(`highlight cue targets unknown marker ${focus.target}`)
  const target = focusCamera(iw, ih, fw, fh, fractionBox(marker.box, iw, ih))
  return blendCamera(cameraAt(keys, t(focus.frame)), target, progress(frame, focus.frame, FOCUS_FRAMES))
}

export function checkPhotoPlate(p: PhotoPlateProps): string[] {
  return p.image.markers
    .filter((m) => m.box[2] <= 0 || m.box[3] <= 0 || m.box[0] + m.box[2] > 1 || m.box[1] + m.box[3] > 1)
    .map((m) => `marker ${m.id} box ${JSON.stringify(m.box)} is not a box inside the image (fractions 0..1)`)
}

export const PhotoPlate: React.FC<BlockProps<PhotoPlateProps>> = ({ props: p, cues, durationInFrames, sceneId }) => {
  const frame = useCurrentFrame()
  const { width: fw, height: fh } = useVideoConfig()
  const { imageSizes } = useEpisode()
  const size = imageSize(imageSizes, p.image.src)
  const [iw, ih] = size
  const view = viewFor(iw, ih, fw, fh, plateCamera(p.image, size, p.kenBurns ?? 'in', cues, frame, durationInFrames, fw, fh))
  const focused = cues.filter((c) => c.do === 'highlight' && c.frame <= frame).map((c) => c.target)
  const marks = p.image.markers
    .filter((m) => visibleAt(cues, m.id, frame))
    .map((m) => ({ id: m.id, box: fractionBox(m.box, iw, ih), label: m.label, appear: firstCue(cues, 'show', m.id) ?? 0, focused: focused.includes(m.id), shape: 'ring' as const }))
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <ImageLayer sceneId={sceneId} src={p.image.src} width={iw} height={ih} view={view} marks={marks} />
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
      {p.caption ? (
        <LayoutBox
          id={`${sceneId}:caption`}
          kind="text"
          style={{ position: 'absolute', left: 1024, top: 846, width: 800, height: 64, overflow: 'hidden', textAlign: 'right', ...body(26, colors.white), ...overFootage, ...bootIn(frame, 10) }}
        >
          {p.caption}
        </LayoutBox>
      ) : null}
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/MapboxTopdown.tsx`** (complete file):

```tsx
/**
 * MapboxTopdown: an exact top-down satellite frame (pipeline/studio/capture/
 * mapbox.py, Mapbox Static API) with its pins at the projected pixels the
 * capture recorded (events named "pin": target = case-file place id, label,
 * x/y in image pixels, lat/lng). Top-down imagery is orthographic, so distance
 * lines between two pins are allowed here; their text is computed from the
 * pins' coordinates, never typed. Cues:
 *   show <place>       the pin appears (without one: staggered from frame 8)
 *   highlight <place>  the camera flies onto the pin and holds
 * Lines draw once both of their pins are up.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { firstCue } from '../cues'
import { formatDistance, haversineM } from '../format'
import { type ImageBox, blendCamera, cameraAt, focusCamera, kenBurnsCamera, viewFor } from '../layout/transform'
import { progress } from '../motion'
import { colors } from '../theme/colors'
import { ImageLayer } from './ImageLayer'
import { LowerThird } from './LowerThird'
import type { BlockProps, Capture, CaptureEvent, Label } from './types'

export type PinLine = { from: string; to: string }
export type MapboxTopdownProps = { map: Capture; lines?: PinLine[]; label?: Label }
export type Pin = { id: string; label: string; x: number; y: number; lat: number; lng: number }

const PIN_BOX = 24

export function pinsOf(map: Capture): Pin[] {
  return map.events
    .filter((e: CaptureEvent) => e.name === 'pin')
    .map((e) => ({ id: e.target as string, label: e.label as string, x: e.x as number, y: e.y as number, lat: e.lat as number, lng: e.lng as number }))
}

export function checkMapboxTopdown(p: MapboxTopdownProps): string[] {
  const pins = pinsOf(p.map)
  const errors: string[] = []
  if (pins.length === 0) errors.push(`capture ${p.map.id} has no pin events`)
  for (const pin of pins) {
    if ([pin.id, pin.label, pin.x, pin.y, pin.lat, pin.lng].some((v) => v === undefined)) errors.push(`capture ${p.map.id}: a pin event lacks target, label, x, y, lat or lng`)
    else if (pin.x < 0 || pin.y < 0 || pin.x > p.map.width || pin.y > p.map.height) errors.push(`pin ${pin.id} lies outside the ${p.map.width}x${p.map.height} image`)
  }
  const ids = new Set(pins.map((pin) => pin.id))
  for (const l of p.lines ?? []) {
    if (!ids.has(l.from) || !ids.has(l.to) || l.from === l.to) errors.push(`line ${l.from} -> ${l.to} must join two different pins of the capture`)
  }
  return errors
}

const pinBox = (pin: Pin): ImageBox => [pin.x - PIN_BOX / 2, pin.y - PIN_BOX / 2, PIN_BOX, PIN_BOX]

export const MapboxTopdown: React.FC<BlockProps<MapboxTopdownProps>> = ({ props: p, cues, durationInFrames, sceneId }) => {
  const frame = useCurrentFrame()
  const { width: fw, height: fh } = useVideoConfig()
  const { width: iw, height: ih } = p.map
  const pins = pinsOf(p.map)
  const t = (f: number) => (durationInFrames > 1 ? f / (durationInFrames - 1) : 0)
  const keys = kenBurnsCamera(iw, ih, 'in')
  let cam = cameraAt(keys, t(frame))
  const focus = cues.filter((c) => c.do === 'highlight' && c.frame <= frame).sort((a, b) => a.frame - b.frame).pop()
  if (focus) {
    const pin = pins.find((x) => x.id === focus.target)
    if (!pin) throw new Error(`highlight cue targets unknown pin ${focus.target}`)
    const area: ImageBox = [pin.x - iw * 0.12, pin.y - ih * 0.12, iw * 0.24, ih * 0.24]
    cam = blendCamera(cameraAt(keys, t(focus.frame)), focusCamera(iw, ih, fw, fh, area), progress(frame, focus.frame, 36))
  }
  const view = viewFor(iw, ih, fw, fh, cam)
  const appear = new Map(pins.map((pin, i) => [pin.id, firstCue(cues, 'show', pin.id) ?? 8 + i * 10]))
  const focused = focus ? focus.target : null
  const marks = pins.map((pin) => ({ id: pin.id, box: pinBox(pin), label: pin.label, appear: appear.get(pin.id) as number, focused: pin.id === focused, shape: 'pin' as const }))
  const byId = new Map(pins.map((pin) => [pin.id, pin]))
  const lines = (p.lines ?? []).map((l) => {
    const a = byId.get(l.from) as Pin
    const b = byId.get(l.to) as Pin
    return {
      id: `${l.from}-${l.to}`,
      from: { x: a.x, y: a.y },
      to: { x: b.x, y: b.y },
      text: formatDistance(haversineM(a, b)),
      appear: Math.max(appear.get(l.from) as number, appear.get(l.to) as number) + 20,
    }
  })
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <ImageLayer sceneId={sceneId} src={p.map.src} width={iw} height={ih} view={view} marks={marks} lines={lines} />
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
    </AbsoluteFill>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/blocks-image.test.ts`
Expected: `Tests  4 passed (4)`

- [ ] **Step 5: Commit**

```bash
git add video/src/blocks/PhotoPlate.tsx video/src/blocks/MapboxTopdown.tsx video/test/blocks-image.test.ts
git commit -m "Add PhotoPlate with markers in the image's own layer and MapboxTopdown with projected pins" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 14: PlatformClip, GlobeShot and MapboxFlyover

**Files:**
- Create: `video/src/blocks/PlatformClip.tsx`, `video/src/blocks/GlobeShot.tsx`, `video/src/blocks/MapboxFlyover.tsx`
- Test: `video/test/blocks-clips.test.ts`

The clip blocks. PlatformClip is a platform moment (the real ancientnerds.com) with a virtual camera: explicit keys on the capture clock, or `follow`, which zooms onto every event with a position (the cursor's clicks). The camera never zooms past the capture's own pixels: the screencast is capped at the display's pixel size (2880x1620 on the workstation), so a close-up stays sharp up to `width / 1920` (1.5x there) and the check refuses more, although the schema allows zoom 3 and follow 2.5 for larger captures. GlobeShot is our vector globe, which carries no third-party map data, so it needs no map credit. Its places come from the capture's `place` events with their per-frame `track` (owner rule: globe markers are projected per frame from their coordinates, so a pin moves with the globe when the camera moves): a labelled place is a pin with its label, lit at its event frame (a cue can only delay it) and hidden while its track entry is null; an unlabelled place (a world distribution) is a small dot. MapboxFlyover takes the Mapbox fly-ins and orbits; the checks keep the two apart by their credits, so the in-frame Mapbox credit is never missing.

- [ ] **Step 1: Write the failing test**

**`video/test/blocks-clips.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { checkGlobeShot, globeDots, globePins, pinAt } from '../src/blocks/GlobeShot'
import { checkMapboxFlyover } from '../src/blocks/MapboxFlyover'
import { FOLLOW_LEAD_S, checkPlatformClip, followKeys, platformCamera } from '../src/blocks/PlatformClip'
import type { Capture } from '../src/blocks/types'

const capture = (over: Partial<Capture>): Capture => ({
  id: 'pf1',
  kind: 'platform',
  src: 'captures/pf1.mp4',
  fps: 60,
  duration_s: 10,
  width: 2880,
  height: 1620,
  events: [],
  credits: ['© Mapbox © OpenStreetMap © Maxar'],
  ...over,
})
const ctx = { fps: 60, durationInFrames: 180 }

describe('PlatformClip camera', () => {
  it('follows the events with a position, easing in before each', () => {
    const events = [{ t: 0.4, name: 'pause_rotation' }, { t: 1, name: 'search', x: 500, y: 700 }, { t: 3, name: 'click_result', x: 400, y: 1800 }]
    expect(followKeys(events, 1.6, 2880, 1620)).toEqual([
      { t: 0, cx: 1440, cy: 810, zoom: 1 },
      { t: 1 - FOLLOW_LEAD_S, cx: 1440, cy: 810, zoom: 1 },
      { t: 1, cx: 500, cy: 700, zoom: 1.6 },
      { t: 3 - FOLLOW_LEAD_S, cx: 500, cy: 700, zoom: 1.6 },
      { t: 3, cx: 400, cy: 1800, zoom: 1.6 },
    ])
  })
  it('interpolates keys on the capture clock and shows the whole frame without keys', () => {
    expect(platformCamera(undefined, 2880, 1620, 3)).toEqual({ cx: 1440, cy: 810, zoom: 1 })
    const keys = [
      { t: 1, cx: 1440, cy: 810, zoom: 1 },
      { t: 2, cx: 600, cy: 240, zoom: 2 },
    ]
    expect(platformCamera(keys, 2880, 1620, 0.5)).toEqual({ cx: 1440, cy: 810, zoom: 1 })
    expect(platformCamera(keys, 2880, 1620, 1.5).zoom).toBeCloseTo(Math.SQRT2)
    expect(platformCamera(keys, 2880, 1620, 2.5)).toEqual({ cx: 600, cy: 240, zoom: 2 })
  })
  it('refuses a camera and follow together, keys outside the capture and keys out of order', () => {
    const clip = capture({})
    expect(checkPlatformClip({ clip, camera: [{ t: 0, cx: 1, cy: 1, zoom: 1 }], follow: 1.5 }, ctx)).toEqual(['camera and follow exclude each other'])
    expect(checkPlatformClip({ clip, camera: [{ t: 0, cx: 3000, cy: 1, zoom: 1 }] }, ctx)).toEqual(['camera key at 0 s points outside the 2880x1620 capture'])
    expect(checkPlatformClip({ clip, camera: [{ t: 2, cx: 1, cy: 1, zoom: 1 }, { t: 1, cx: 1, cy: 1, zoom: 1 }] }, ctx)).toEqual(['camera keys must be in increasing time order'])
  })
  it('never zooms past the pixels of the capture (sharp up to width / 1920)', () => {
    const clip = capture({})
    expect(checkPlatformClip({ clip, follow: 1.5 }, ctx)).toEqual([])
    expect(checkPlatformClip({ clip, follow: 1.6 }, ctx)).toEqual(['zoom 1.6 upscales the 2880x1620 capture (sharp up to 1.50)'])
    expect(checkPlatformClip({ clip, camera: [{ t: 0, cx: 1440, cy: 810, zoom: 2 }] }, ctx)).toEqual(['zoom 2 upscales the 2880x1620 capture (sharp up to 1.50)'])
  })
})

describe('GlobeShot and MapboxFlyover', () => {
  const track = (n: number, at: [number, number] | null = [960, 540]): ([number, number] | null)[] => Array.from({ length: n }, () => at)
  it('reads pins from the labelled place events and dots from the unlabelled ones', () => {
    const globe = capture({
      kind: 'globe',
      credits: [],
      duration_s: 4,
      events: [
        { t: 0, name: 'gpu', label: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU)' },
        { t: 0, name: 'rotate' },
        { t: 3, name: 'place', target: 'p2', x: 10, y: 10, track: track(60, [10, 10]) },
        { t: 3.5, name: 'arrive', x: 960, y: 540 },
        { t: 3.5, name: 'place', target: 'p1', label: 'Baalbek', x: 960, y: 540, track: track(30) },
      ],
    })
    expect(globePins(globe)).toEqual([{ id: 'p1', frame: 210, x: 960, y: 540, label: 'Baalbek', track: track(30) }])
    expect(globeDots(globe)).toEqual([{ id: 'p2', frame: 180, track: track(60, [10, 10]) }])
    expect(checkGlobeShot({ clip: globe }, ctx)).toEqual([])
  })
  it('moves a pin along its track, hides it on null and never shows it before its event frame', () => {
    const pin = { frame: 100, track: [[10, 20], null, [14, 22]] as ([number, number] | null)[] }
    expect(pinAt(pin, 99)).toBeNull()
    expect(pinAt(pin, 100)).toEqual({ x: 10, y: 20 })
    expect(pinAt(pin, 101)).toBeNull()
    expect(pinAt(pin, 102)).toEqual({ x: 14, y: 22 })
  })
  it('refuses a place event without a track that runs to the end of the take', () => {
    const place = { t: 3.5, name: 'place', target: 'p1', label: 'Baalbek', x: 960, y: 540 }
    const short = capture({ kind: 'globe', credits: [], duration_s: 4, events: [{ ...place, track: track(12) }] })
    expect(checkGlobeShot({ clip: short }, ctx)).toEqual(['place p1: the track holds 12 points, the take has 30 frames from the event on'])
    const none = capture({ kind: 'globe', credits: [], duration_s: 4, events: [place] })
    expect(checkGlobeShot({ clip: none }, ctx)).toEqual(['place p1 has no track (re-capture the take)'])
  })
  it('keeps Mapbox takes out of GlobeShot and our globe out of MapboxFlyover', () => {
    const mapboxTake = capture({ id: 'm1', kind: 'globe', width: 1920, height: 1080 })
    expect(checkGlobeShot({ clip: mapboxTake }, ctx)).toEqual(['capture m1 carries map credits: a Mapbox take belongs in MapboxFlyover'])
    expect(checkMapboxFlyover({ clip: { ...mapboxTake, credits: [] } }, ctx)).toEqual(['capture m1 has no Mapbox credit: our vector globe belongs in GlobeShot'])
    expect(checkMapboxFlyover({ clip: mapboxTake }, ctx)).toEqual([])
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/blocks-clips.test.ts`
Expected: FAIL with `Cannot find module '../src/blocks/GlobeShot'`.

- [ ] **Step 3: Implement**

**`video/src/blocks/PlatformClip.tsx`** (complete file):

```tsx
/**
 * PlatformClip: a platform moment, the real ancientnerds.com recorded by
 * pipeline/studio/capture/platform.py (1920x1080 CSS px at device scale 2; the
 * screencast delivers up to the display's pixel size, e.g. 2880x1620, at a
 * constant 60 fps), full bleed with a virtual camera:
 *   camera  explicit keys on the capture clock (t = clip seconds, cx/cy = capture pixels)
 *   follow  zoom onto every event with x/y (the cursor's clicks), easing in 0.35 s before it
 *   neither the whole frame
 * The in-frame map credit comes from the capture manifest via timeline.credits.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { type Camera, type CameraKey, cameraAt, viewFor } from '../layout/transform'
import { colors } from '../theme/colors'
import { clipProblems, clipTime, trimFrames } from './clips'
import { Footage } from './Footage'
import { LowerThird } from './LowerThird'
import type { BlockProps, Capture, CaptureEvent, CheckContext, Label } from './types'

export type PlatformCameraKey = { t: number; cx: number; cy: number; zoom: number }
export type PlatformClipProps = { clip: Capture; start_s?: number; camera?: PlatformCameraKey[]; follow?: number; label?: Label }

/** Seconds the camera takes to reach an event it follows. */
export const FOLLOW_LEAD_S = 0.35

/** Camera keys (on the capture clock) that zoom onto each event with a position. */
export function followKeys(events: readonly CaptureEvent[], zoom: number, width: number, height: number): PlatformCameraKey[] {
  const keys: PlatformCameraKey[] = [{ t: 0, cx: width / 2, cy: height / 2, zoom: 1 }]
  for (const e of events) {
    if (e.x === undefined || e.y === undefined) continue
    const last = keys[keys.length - 1]
    const holdAt = Math.max(last.t, e.t - FOLLOW_LEAD_S)
    if (holdAt > last.t) keys.push({ ...last, t: holdAt })
    keys.push({ t: Math.max(e.t, holdAt), cx: e.x, cy: e.y, zoom })
  }
  return keys
}

/** Camera at capture time `time` (seconds): the keys eased on the capture clock; the whole frame without keys. */
export function platformCamera(keys: readonly PlatformCameraKey[] | undefined, width: number, height: number, time: number): Camera {
  if (!keys || keys.length === 0) return { cx: width / 2, cy: height / 2, zoom: 1 }
  const asKeys: CameraKey[] = keys.map((k) => ({ at: k.t, cx: k.cx, cy: k.cy, zoom: k.zoom }))
  return cameraAt(asKeys, time)
}

export function checkPlatformClip(p: PlatformClipProps, ctx: CheckContext): string[] {
  const errors = clipProblems(p.clip, p.start_s ?? 0, ctx)
  if (p.camera && p.follow !== undefined) errors.push('camera and follow exclude each other')
  for (const k of p.camera ?? []) {
    if (k.cx > p.clip.width || k.cy > p.clip.height) errors.push(`camera key at ${k.t} s points outside the ${p.clip.width}x${p.clip.height} capture`)
  }
  const times = (p.camera ?? []).map((k) => k.t)
  if (times.some((t, i) => i > 0 && t <= times[i - 1])) errors.push('camera keys must be in increasing time order')
  // The screencast is capped at the display's pixel size: past width / 1920 the camera would upscale it.
  const sharp = p.clip.width / 1920
  const zooms = [...(p.camera ?? []).map((k) => k.zoom), ...(p.follow === undefined ? [] : [p.follow])]
  for (const z of zooms) {
    if (z > sharp + 1e-9) errors.push(`zoom ${z} upscales the ${p.clip.width}x${p.clip.height} capture (sharp up to ${sharp.toFixed(2)})`)
  }
  return errors
}

export const PlatformClip: React.FC<BlockProps<PlatformClipProps>> = ({ props: p, sceneId }) => {
  const frame = useCurrentFrame()
  const { fps, width: fw, height: fh } = useVideoConfig()
  const start = p.start_s ?? 0
  const keys = p.follow !== undefined ? followKeys(p.clip.events, p.follow, p.clip.width, p.clip.height) : p.camera
  const view = viewFor(p.clip.width, p.clip.height, fw, fh, platformCamera(keys, p.clip.width, p.clip.height, clipTime(start, frame, fps)))
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <div style={{ position: 'absolute', left: 0, top: 0, width: p.clip.width, height: p.clip.height, transformOrigin: '0 0', transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})` }}>
        <Footage src={p.clip.src} trimBefore={trimFrames(start, fps)} style={{ width: p.clip.width, height: p.clip.height }} />
      </div>
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/GlobeShot.tsx`** (complete file):

```tsx
/**
 * GlobeShot: our vector globe recorded frame by frame by the Puppeteer
 * recorder (pipeline/studio/capture/globe.py: studio-globe-flyto and
 * studio-globe-places, 1920x1080 at 60 fps). The globe carries no third-party
 * map data, so a GlobeShot needs no map credit; Mapbox takes belong in
 * MapboxFlyover. Places come from the capture's "place" events: the pixel the
 * page drew the place at in every capture frame from the event on (`track`,
 * null while the place is behind the globe or outside the label band), so a
 * place moves with the globe when the camera moves (owner rule: globe markers
 * are projected per frame from their coordinates). A labelled place is a pin
 * with its label, lit at its event frame; a show <place> cue can only delay it.
 * An unlabelled place (a world distribution) is a small dot. The fly-to's
 * "arrive" event carries no label and draws nothing.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { firstCue } from '../cues'
import { LayoutBox } from '../layout/LayoutBox'
import { toScreen, viewFor } from '../layout/transform'
import { bootIn, progress, ringPulse } from '../motion'
import { colors } from '../theme/colors'
import { hud, overFootage } from '../theme/type'
import { FPS } from '../timeline'
import { clipProblems, trimFrames } from './clips'
import { Footage } from './Footage'
import { LowerThird } from './LowerThird'
import type { BlockProps, Capture, CaptureEvent, CheckContext, Label } from './types'

export type GlobeShotProps = { clip: Capture; start_s?: number; label?: Label }
export type Track = ([number, number] | null)[]
/** A labelled place: `frame` is the capture frame of its event (captures run at the timeline's 60 fps). */
export type GlobePin = { id: string; frame: number; x: number; y: number; label: string; track: Track }
export type GlobeDot = { id: string; frame: number; track: Track }

const DOT = 12

type PlaceEvent = CaptureEvent & { target: string; x: number; y: number }

function placeEvents(clip: Capture): PlaceEvent[] {
  return clip.events.filter((e): e is PlaceEvent => e.name === 'place' && e.target !== undefined && e.x !== undefined && e.y !== undefined)
}

/** The labelled places: pins with their label. */
export function globePins(clip: Capture): GlobePin[] {
  return placeEvents(clip)
    .filter((e) => e.label !== undefined)
    .map((e) => ({ id: e.target, frame: Math.round(e.t * FPS), x: e.x, y: e.y, label: e.label as string, track: e.track ?? [] }))
}

/** The unlabelled places of a world distribution: dots without a label. */
export function globeDots(clip: Capture): GlobeDot[] {
  return placeEvents(clip)
    .filter((e) => e.label === undefined)
    .map((e) => ({ id: e.target, frame: Math.round(e.t * FPS), track: e.track ?? [] }))
}

/** Where a place sits at capture frame `clipFrame`: its track entry; null before its event frame and while hidden. */
export function pinAt(place: { frame: number; track: readonly ([number, number] | null)[] }, clipFrame: number): { x: number; y: number } | null {
  if (clipFrame < place.frame) return null
  const at = place.track[clipFrame - place.frame]
  return at ? { x: at[0], y: at[1] } : null
}

export function checkGlobeShot(p: GlobeShotProps, ctx: CheckContext): string[] {
  const errors = clipProblems(p.clip, p.start_s ?? 0, ctx)
  if (p.clip.credits.length > 0) errors.push(`capture ${p.clip.id} carries map credits: a Mapbox take belongs in MapboxFlyover`)
  if (p.clip.duration_s === null) return errors
  const frames = Math.round(p.clip.duration_s * FPS)
  for (const e of placeEvents(p.clip)) {
    const rest = frames - Math.round(e.t * FPS)
    if (!e.track) errors.push(`place ${e.target} has no track (re-capture the take)`)
    else if (e.track.length !== rest) errors.push(`place ${e.target}: the track holds ${e.track.length} points, the take has ${rest} frames from the event on`)
    else if (e.track.some((pt) => pt !== null && (pt[0] < 0 || pt[1] < 0 || pt[0] > p.clip.width || pt[1] > p.clip.height))) {
      errors.push(`place ${e.target} leaves the ${p.clip.width}x${p.clip.height} capture`)
    }
  }
  return errors
}

export const GlobeShot: React.FC<BlockProps<GlobeShotProps>> = ({ props: p, cues, sceneId }) => {
  const frame = useCurrentFrame()
  const { fps, width: fw, height: fh } = useVideoConfig()
  const trim = trimFrames(p.start_s ?? 0, fps)
  const clipFrame = trim + frame
  const view = viewFor(p.clip.width, p.clip.height, fw, fh, { cx: p.clip.width / 2, cy: p.clip.height / 2, zoom: 1 })
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <Footage src={p.clip.src} trimBefore={trim} style={{ width: '100%', height: '100%' }} />
      {globeDots(p.clip).map((dot) => {
        const pos = pinAt(dot, clipFrame)
        if (!pos) return null
        const at = toScreen(view, pos.x, pos.y)
        return <div key={dot.id} style={{ position: 'absolute', left: at.x - DOT / 2, top: at.y - DOT / 2, width: DOT, height: DOT, borderRadius: DOT / 2, background: colors.green, boxShadow: `0 0 8px ${colors.green}`, opacity: progress(frame, dot.frame - trim, 12) }} />
      })}
      {globePins(p.clip).map((pin) => {
        // A pin follows its track from its event frame on (never before it): a cue can only delay it.
        const eventFrame = pin.frame - trim
        const appear = Math.max(eventFrame, firstCue(cues, 'show', pin.id) ?? eventFrame)
        if (frame < appear) return null
        const pos = pinAt(pin, clipFrame)
        if (!pos) return null
        const ring = ringPulse(frame, appear)
        const at = toScreen(view, pos.x, pos.y)
        const ringId = `${sceneId}:pin:${pin.id}`
        const labelId = `${sceneId}:pinlabel:${pin.id}`
        return (
          <React.Fragment key={pin.id}>
            <LayoutBox id={ringId} kind="mark" allow={[labelId]} style={{ position: 'absolute', left: at.x - 12, top: at.y - 12, width: 24, height: 24 }}>
              <div style={{ position: 'absolute', inset: 0, borderRadius: 12, background: colors.green, boxShadow: `0 0 12px ${colors.green}` }} />
              <div style={{ position: 'absolute', inset: 0, borderRadius: 12, border: `3px solid ${colors.green}`, transform: `scale(${ring.scale * 2.2})`, opacity: ring.opacity }} />
            </LayoutBox>
            <div style={{ position: 'absolute', left: at.x + 24, top: at.y - 22, ...bootIn(frame, appear + 4, 12) }}>
              <LayoutBox id={labelId} kind="text" allow={[ringId]} style={{ ...hud(28, colors.white), whiteSpace: 'nowrap', ...overFootage }}>
                {pin.label}
              </LayoutBox>
            </div>
          </React.Fragment>
        )
      })}
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/MapboxFlyover.tsx`** (complete file):

```tsx
/**
 * MapboxFlyover: a Mapbox satellite fly-in or orbit, recorded frame by frame
 * by the recorder (studio-mapbox-flyin / studio-mapbox-orbit). The in-frame
 * credit comes from the capture manifest via timeline.credits (CreditLine).
 */
import React from 'react'
import { AbsoluteFill, useVideoConfig } from 'remotion'

import { colors } from '../theme/colors'
import { clipProblems, trimFrames } from './clips'
import { Footage } from './Footage'
import { LowerThird } from './LowerThird'
import type { BlockProps, Capture, CheckContext, Label } from './types'

export type MapboxFlyoverProps = { clip: Capture; start_s?: number; label?: Label }

export function checkMapboxFlyover(p: MapboxFlyoverProps, ctx: CheckContext): string[] {
  const errors = clipProblems(p.clip, p.start_s ?? 0, ctx)
  if (!p.clip.credits.some((c) => c.includes('© Mapbox'))) errors.push(`capture ${p.clip.id} has no Mapbox credit: our vector globe belongs in GlobeShot`)
  return errors
}

export const MapboxFlyover: React.FC<BlockProps<MapboxFlyoverProps>> = ({ props: p, sceneId }) => {
  const { fps } = useVideoConfig()
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <Footage src={p.clip.src} trimBefore={trimFrames(p.start_s ?? 0, fps)} style={{ width: '100%', height: '100%' }} />
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
    </AbsoluteFill>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/blocks-clips.test.ts`
Expected: `Tests  8 passed (8)`

- [ ] **Step 5: Commit**

```bash
git add video/src/blocks/PlatformClip.tsx video/src/blocks/GlobeShot.tsx video/src/blocks/MapboxFlyover.tsx video/test/blocks-clips.test.ts
git commit -m "Add the clip blocks: platform moments with a virtual camera, globe shots with pins, Mapbox fly-ins" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 15: The case-file cards: evidence, quote, source page, claims, meter, list, share

**Files:**
- Create: `video/src/blocks/EvidenceCard.tsx`, `video/src/blocks/QuoteCard.tsx`, `video/src/blocks/SourceViewer.tsx`, `video/src/blocks/ClaimBoard.tsx`, `video/src/blocks/Meter.tsx`, `video/src/blocks/ListCard.tsx`, `video/src/blocks/ShareCard.tsx`
- Test: `video/test/blocks-cards.test.ts`

The Case File spine: an EvidenceCard types its verbatim quote on and stamps VERIFIED (only verified evidence reaches a script); a status cue for its claim slams the new status on the card. SourceViewer scrolls the captured source page until the highlighted quote sits a third from the top. ClaimBoard and Meter read the episode-wide state (Task 9). ListCard carries "what would change our mind"; ShareCard is the one place the link appears in the picture and is allowed only as the last scene (owner rule; Task 17's `checkBlocks` enforces it).

- [ ] **Step 1: Write the failing test**

**`video/test/blocks-cards.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { boardLayout, claimAppear } from '../src/blocks/ClaimBoard'
import { cardLayout } from '../src/blocks/EvidenceCard'
import { checkMeter, meterTop } from '../src/blocks/Meter'
import { checkQuoteCard } from '../src/blocks/QuoteCard'
import { checkSourceViewer, defaultScroll, pageInfo, scrollAt, windowRect } from '../src/blocks/SourceViewer'
import type { Capture, Evidence } from '../src/blocks/types'
import { ZONES } from '../src/layout/zones'

const evidence: Evidence = {
  id: 'e1',
  claim_id: 'c1',
  kind: 'quantity',
  statement: 'The Stone of the Pregnant Woman weighs about 1,000 tonnes.',
  source: { url: 'https://www.dainst.org/baalbek-report', title: 'DAI report', tier: 1, license: '', quote: 'estimated to weigh 1,650 tonnes', locator: 'section 2' },
  paper_anchor: 'ev-01',
}
const page: Capture = {
  id: 'src1',
  kind: 'source',
  src: 'captures/src1.png',
  fps: null,
  duration_s: null,
  width: 2560,
  height: 3686,
  events: [
    { t: 0, name: 'page', url: 'https://en.wikipedia.org/wiki/Baalbek', title: 'Baalbek - Wikipedia' },
    { t: 0, name: 'highlight', box: [528, 1800, 1489, 86], target: 'quote' },
  ],
  credits: [],
}

describe('EvidenceCard', () => {
  it('shares the free height 45:55 between statement and quote', () => {
    const l = cardLayout(660)
    expect(l.statement.y).toBe(102)
    expect(l.quote.y).toBe(l.statement.y + l.statement.h + 18)
    expect(l.quote.y + l.quote.h + 18).toBe(l.source.y)
  })
})

describe('QuoteCard', () => {
  it('needs a verbatim quote', () => {
    expect(checkQuoteCard({ evidence })).toEqual([])
    expect(checkQuoteCard({ evidence: { ...evidence, source: { ...evidence.source, quote: ' ' } } })).toEqual(['evidence e1 has no verbatim quote to show'])
  })
})

describe('SourceViewer', () => {
  it('reads the url and the highlight box from the capture events; the page title stays a record', () => {
    expect(pageInfo(page)).toEqual({ url: 'https://en.wikipedia.org/wiki/Baalbek', box: [528, 1800, 1489, 86] })
    expect(checkSourceViewer({ page, evidence })).toEqual([])
    expect(checkSourceViewer({ page: { ...page, events: [] }, evidence })).toEqual(['capture src1 has no page event with a url', 'capture src1 has no highlight event with a box'])
  })
  it('brings the quote from low in the window to 35 % from the top', () => {
    const win = windowRect(ZONES.stage)
    const keys = defaultScroll(2560, 4000, 2000, win)
    const viewport = ((win.h - 52) * 2560) / win.w
    expect(keys[0].y).toBeCloseTo(2000 - viewport * 0.8)
    expect(scrollAt(keys, 1)).toBeCloseTo(2000 - viewport * 0.35)
  })
})

describe('ClaimBoard', () => {
  it('lets claims appear at their introduce cue, earlier ones at once, later ones not yet', () => {
    expect(claimAppear(undefined, 2, 0, 100)).toBe(28)
    expect(claimAppear(40, 0, 0, 100)).toBe(40)
    expect(claimAppear(10, 0, 200, 300)).toBe(0)
    expect(claimAppear(400, 0, 200, 300)).toBeNull()
  })
  it('makes the rows as tall as the stage allows and centres them', () => {
    expect(boardLayout(2, 230, 820)).toEqual({ rowH: 190, labelSize: 46, top: 335 })
    expect(boardLayout(6, 230, 820)).toEqual({ rowH: 98, labelSize: 30, top: 231 })
  })
})

describe('Meter', () => {
  it('needs a start split summing to 100 and centres its stack', () => {
    expect(checkMeter({ hypotheses: ['Roman engineers', 'A lost older civilization'], start: [50, 50] })).toEqual([])
    expect(checkMeter({ hypotheses: ['a', 'b'], start: [60, 30] })).toEqual(['meter start [60,30] must sum to 100'])
    expect(meterTop(140, 680, false)).toBeGreaterThan(meterTop(140, 680, true))
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/blocks-cards.test.ts`
Expected: FAIL with `Cannot find module '../src/blocks/ClaimBoard'`.

- [ ] **Step 3: Implement**

**`video/src/blocks/EvidenceCard.tsx`** (complete file):

```tsx
/**
 * EvidenceCard: one sourced evidence item of the case file: what it is, the
 * statement, the verbatim quote from the source (types on at its highlight
 * <evidence id> cue, else at frame 24), the source line (domain, tier,
 * locator, paper anchor) and a VERIFIED stamp (stamp <evidence id> cue, else
 * 70 % into the scene; only verified evidence reaches a script). A status cue
 * for the evidence's claim in this scene slams the claim's new status on the card.
 */
import React from 'react'
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from 'remotion'

import { firstCue, latestCue } from '../cues'
import { domainOf } from '../format'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, typeOn } from '../motion'
import { type ClaimStatus, colors, statusColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { Panel } from './Panel'
import { Stamp } from './Stamp'
import type { BlockProps, Evidence, Media } from './types'

export type EvidenceCardProps = { evidence: Evidence; image?: Media }

const PAD = 48
const GAP = 18
const HEAD_H = 36
const SOURCE_H = 80
const IMAGE_W = 500
const STAMP_COLUMN = 360

/** Vertical layout of the card's text inside a panel of height h: statement 45 %, quote 55 % of the free space. */
export function cardLayout(h: number): { statement: Rect; quote: Rect; source: Rect } {
  const free = h - 2 * PAD - HEAD_H - SOURCE_H - 3 * GAP
  const statementH = Math.floor(free * 0.45)
  const quoteH = free - statementH
  const statementY = PAD + HEAD_H + GAP
  const quoteY = statementY + statementH + GAP
  return {
    statement: { x: PAD, y: statementY, w: 0, h: statementH },
    quote: { x: PAD, y: quoteY, w: 0, h: quoteH },
    source: { x: PAD, y: h - PAD - SOURCE_H, w: 0, h: SOURCE_H },
  }
}

export const EvidenceCard: React.FC<BlockProps<EvidenceCardProps>> = ({ props: p, cues, durationInFrames, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const e = p.evidence
  const panel = { x: stage.x + 60, y: stage.y + 10, w: stage.w - 120, h: stage.h - 20 }
  const layout = cardLayout(panel.h)
  // The right column holds the image (if any) and the stamps; the text keeps clear of it.
  const textW = panel.w - 2 * PAD - (p.image ? IMAGE_W + PAD : STAMP_COLUMN)
  const quoteAt = firstCue(cues, 'highlight', e.id) ?? 24
  const stampAt = firstCue(cues, 'stamp', e.id) ?? Math.round(durationInFrames * 0.7)
  const status = latestCue(cues, 'status', e.claim_id, frame)
  const quote = e.source.quote
  const typed = typeOn(quote, frame, quoteAt, 2)
  const source = [domainOf(e.source.url), `tier ${e.source.tier}`, e.source.locator, e.paper_anchor ? `paper #${e.paper_anchor}` : ''].filter(Boolean).join('  //  ')
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <Panel rect={panel}>
        <LayoutBox id={`${sceneId}:head`} kind="text" style={{ position: 'absolute', left: PAD, top: PAD, width: textW, height: HEAD_H, overflow: 'hidden', whiteSpace: 'nowrap', ...hud(24), ...bootIn(frame, 6) }}>
          {`Evidence // ${e.kind}`}
        </LayoutBox>
        <LayoutBox
          id={`${sceneId}:statement`}
          kind="text"
          style={{ position: 'absolute', left: PAD, top: layout.statement.y, width: textW, height: layout.statement.h, overflow: 'hidden', ...heading(40), textTransform: 'none', letterSpacing: '0.02em', ...bootIn(frame, 10) }}
        >
          {e.statement}
        </LayoutBox>
        {quote ? (
          <LayoutBox
            id={`${sceneId}:quote`}
            kind="text"
            style={{ position: 'absolute', left: PAD, top: layout.quote.y, width: textW, height: layout.quote.h, overflow: 'hidden', ...body(32, colors.crt300), borderLeft: `4px solid ${colors.green}`, paddingLeft: 22, boxSizing: 'border-box' }}
          >
            {`“${typed}${typed.length === quote.length ? '”' : ''}`}
          </LayoutBox>
        ) : null}
        <LayoutBox id={`${sceneId}:source`} kind="text" style={{ position: 'absolute', left: PAD, top: layout.source.y, width: textW, height: SOURCE_H, overflow: 'hidden', ...bootIn(frame, 16) }}>
          <div style={{ ...body(24, colors.text), whiteSpace: 'nowrap', overflow: 'hidden' }}>{e.source.title}</div>
          <div style={{ ...hud(18, colors.crt400), whiteSpace: 'nowrap', overflow: 'hidden' }}>{source}</div>
        </LayoutBox>
        {p.image ? (
          <div style={{ position: 'absolute', left: panel.w - PAD - IMAGE_W, top: PAD, width: IMAGE_W, height: panel.h - 2 * PAD - 110, overflow: 'hidden', border: `1px solid ${colors.greenDim}`, ...bootIn(frame, 12) }}>
            <Img src={staticFile(p.image.src)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
        ) : null}
      </Panel>
      <Stamp id={`${sceneId}:verified`} text="Verified" color={colors.okGreen} start={stampAt} size={30} style={{ left: panel.x + panel.w - 330, top: panel.y + panel.h - 100 }} />
      {status ? (
        <Stamp
          id={`${sceneId}:status`}
          text={String(status.value)}
          color={statusColor[status.value as ClaimStatus]}
          start={status.frame}
          size={30}
          style={{ left: panel.x + panel.w - 330, top: panel.y + panel.h - 230 }}
        />
      ) : null}
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/QuoteCard.tsx`** (complete file):

```tsx
/**
 * QuoteCard: a verbatim passage from the case file's evidence, for texts and
 * traditions (type D) and for sources whose page cannot be captured (paywall or
 * login). The quote, set in the site's serif, types on at its highlight
 * <evidence id> cue (default frame 12); the source line names work, locator and tier.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { domainOf } from '../format'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, typeOn } from '../motion'
import { colors } from '../theme/colors'
import { body, hud, serif } from '../theme/type'
import { Panel } from './Panel'
import type { BlockProps, Evidence } from './types'

export type QuoteCardProps = { evidence: Evidence; attribution?: string }

const PAD = 64
const SOURCE_H = 96

export function checkQuoteCard(p: QuoteCardProps): string[] {
  return p.evidence.source.quote.trim() ? [] : [`evidence ${p.evidence.id} has no verbatim quote to show`]
}

export const QuoteCard: React.FC<BlockProps<QuoteCardProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const e = p.evidence
  const panel = { x: stage.x + 100, y: stage.y + 10, w: stage.w - 200, h: stage.h - 20 }
  const at = firstCue(cues, 'highlight', e.id) ?? 12
  const quote = e.source.quote
  const typed = typeOn(quote, frame, at, 2)
  const work = p.attribution ? `${p.attribution}, ${e.source.title}` : e.source.title
  const meta = [e.source.locator, domainOf(e.source.url), `tier ${e.source.tier}`].filter(Boolean).join('  //  ')
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <Panel rect={panel}>
        <LayoutBox
          id={`${sceneId}:quote`}
          kind="text"
          style={{ position: 'absolute', left: PAD, top: PAD, width: panel.w - 2 * PAD, height: panel.h - 2 * PAD - SOURCE_H - 20, overflow: 'hidden', ...serif(52), display: 'flex', alignItems: 'center' }}
        >
          <div>{`“${typed}${typed.length === quote.length ? '”' : ''}`}</div>
        </LayoutBox>
        <LayoutBox id={`${sceneId}:source`} kind="text" style={{ position: 'absolute', left: PAD, top: panel.h - PAD - SOURCE_H, width: panel.w - 2 * PAD, height: SOURCE_H, overflow: 'hidden', ...bootIn(frame, at + 10) }}>
          <div style={{ ...body(30, colors.white), whiteSpace: 'nowrap', overflow: 'hidden' }}>{work}</div>
          <div style={{ ...hud(20, colors.crt400), whiteSpace: 'nowrap', overflow: 'hidden' }}>{meta}</div>
        </LayoutBox>
      </Panel>
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/SourceViewer.tsx`** (complete file):

```tsx
/**
 * SourceViewer: a captured source page (pipeline/studio/capture/sources.py:
 * 1280 CSS px wide at device scale 2, the quote already highlighted in the page,
 * banners removed) inside a browser frame filling the stage. The page scrolls
 * from the quote low in the window up to 35 % from the top; an outline glows
 * around the highlighted quote from its highlight <evidence id> cue (default
 * 40 % into the scene). The capture's "page" event carries the URL, whose ASCII
 * hostname is all the address bar draws (the page's own <title> in that event is
 * a record only, never drawn: owner decision 32, so a Greek or Chinese source page
 * shows as captured), its "highlight" event the quote's box in image pixels.
 */
import React from 'react'
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { domainOf } from '../format'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, crtOpen, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, hud } from '../theme/type'
import type { BlockProps, Capture, Evidence } from './types'

export type SourceViewerProps = { page: Capture; evidence: Evidence }
export type ScrollKey = { at: number; y: number }

const BAR = 52
const CAPTION_H = 44

export function windowRect(stage: Rect): Rect {
  return { x: stage.x + 40, y: stage.y, w: stage.w - 80, h: stage.h - CAPTION_H - 20 }
}

/** The page's url and the highlight box from the capture events. */
export function pageInfo(page: Capture): { url: string; box: [number, number, number, number] } {
  const meta = page.events.find((e) => e.name === 'page')
  const hl = page.events.find((e) => e.name === 'highlight')
  if (!meta?.url || !hl?.box) throw new Error(`capture ${page.id} lacks its page or highlight event`)
  return { url: meta.url, box: hl.box }
}

export function checkSourceViewer(p: SourceViewerProps): string[] {
  const meta = p.page.events.find((e) => e.name === 'page')
  const hl = p.page.events.find((e) => e.name === 'highlight')
  const errors: string[] = []
  if (!meta?.url) errors.push(`capture ${p.page.id} has no page event with a url`)
  if (!hl?.box) errors.push(`capture ${p.page.id} has no highlight event with a box`)
  else if (hl.box[0] + hl.box[2] > p.page.width || hl.box[1] + hl.box[3] > p.page.height) errors.push(`the highlight of ${p.page.id} lies outside the page image`)
  return errors
}

/** Page scroll (image pixels at the window's top) from the quote low in the window to 35 % from the top. */
export function defaultScroll(pageW: number, pageH: number, quoteY: number, win: Rect): ScrollKey[] {
  const viewport = ((win.h - BAR) * pageW) / win.w
  const maxY = Math.max(0, pageH - viewport)
  const clamp = (y: number) => Math.min(maxY, Math.max(0, y))
  return [
    { at: 0, y: clamp(quoteY - viewport * 0.8) },
    { at: 0.45, y: clamp(quoteY - viewport * 0.35) },
    { at: 1, y: clamp(quoteY - viewport * 0.35) },
  ]
}

export function scrollAt(keys: readonly ScrollKey[], t: number): number {
  if (t <= keys[0].at) return keys[0].y
  for (let i = 1; i < keys.length; i++) {
    if (t <= keys[i].at) {
      const u = (t - keys[i - 1].at) / Math.max(keys[i].at - keys[i - 1].at, 1e-6)
      return keys[i - 1].y + (keys[i].y - keys[i - 1].y) * u * u * (3 - 2 * u)
    }
  }
  return keys[keys.length - 1].y
}

export const SourceViewer: React.FC<BlockProps<SourceViewerProps>> = ({ props: p, cues, durationInFrames, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const win = windowRect(stage)
  const { url, box } = pageInfo(p.page)
  const scale = win.w / p.page.width
  const y = scrollAt(defaultScroll(p.page.width, p.page.height, box[1], win), durationInFrames > 1 ? frame / (durationInFrames - 1) : 0)
  const glowAt = firstCue(cues, 'highlight', p.evidence.id) ?? Math.round(durationInFrames * 0.4)
  const glow = progress(frame, glowAt, 14)
  const [hx, hy, hw, hh] = box
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <div style={{ position: 'absolute', left: win.x, top: win.y, width: win.w, height: win.h, overflow: 'hidden', border: `1px solid ${colors.greenDim}`, background: '#ffffff', transformOrigin: 'center', ...crtOpen(frame, 0) }}>
        <div style={{ position: 'absolute', left: 0, top: 0, width: win.w, height: BAR, background: '#16202a', display: 'flex', alignItems: 'center', paddingLeft: 20, gap: 10 }}>
          {[colors.red, colors.amber, colors.okGreen].map((c) => (
            <div key={c} style={{ width: 12, height: 12, borderRadius: 6, background: c }} />
          ))}
          <LayoutBox id={`${sceneId}:url`} kind="text" style={{ marginLeft: 20, width: win.w - 180, height: 32, overflow: 'hidden', whiteSpace: 'nowrap', ...body(22, colors.crt300), lineHeight: '32px' }}>
            {domainOf(url)}
          </LayoutBox>
        </div>
        <div style={{ position: 'absolute', left: 0, top: BAR, width: win.w, height: win.h - BAR, overflow: 'hidden' }}>
          <div style={{ position: 'absolute', left: 0, top: 0, width: p.page.width, height: p.page.height, transformOrigin: '0 0', transform: `scale(${scale}) translateY(${-y}px)` }}>
            <Img src={staticFile(p.page.src)} style={{ position: 'absolute', left: 0, top: 0, width: p.page.width, height: p.page.height }} />
            <div
              style={{
                position: 'absolute',
                left: hx - 14,
                top: hy - 14,
                width: hw + 28,
                height: hh + 28,
                border: `${4 / scale}px solid ${colors.green}`,
                borderRadius: 8 / scale,
                opacity: glow,
                boxShadow: `0 0 ${26 / scale}px ${colors.green}`,
              }}
            />
          </div>
        </div>
      </div>
      <LayoutBox
        id={`${sceneId}:caption`}
        kind="text"
        style={{ position: 'absolute', left: win.x, top: win.y + win.h + 14, width: win.w, height: CAPTION_H, overflow: 'hidden', whiteSpace: 'nowrap', ...hud(22, colors.crt400), lineHeight: `${CAPTION_H}px`, ...bootIn(frame, 10) }}
      >
        {`Source page // tier ${p.evidence.source.tier} // quote highlighted`}
      </LayoutBox>
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/ClaimBoard.tsx`** (complete file):

```tsx
/**
 * ClaimBoard: the claims under test, in rows that fill the stage. Its state is
 * episode-wide (state.ts): a claim appears at its introduce cue, whichever scene
 * carried it (claims without any introduce cue enter staggered at the scene
 * start); a status cue recolours it and slams the new status as a stamp. A
 * board shown later in the episode shows everything cued before it. The local
 * cue highlight <claim id> outlines the row.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { useEpisode } from '../context'
import { firstCue } from '../cues'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { claimStatusAt } from '../state'
import { colors, statusColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { Icon } from './icons'
import { Stamp } from './Stamp'
import type { BlockProps, Claim } from './types'

export type ClaimBoardProps = { claims: Claim[]; title?: string }

const TITLE_H = 60
const STATUS_W = 380
const MAX_ROW_H = 190

/** Row height, label size and the first row's top: rows as tall as the stage allows, the block centred in it. */
export function boardLayout(count: number, areaTop: number, areaBottom: number): { rowH: number; labelSize: number; top: number } {
  const rowH = Math.min(MAX_ROW_H, Math.floor((areaBottom - areaTop) / count))
  const labelSize = rowH >= 160 ? 46 : rowH >= 120 ? 38 : 30
  return { rowH, labelSize, top: areaTop + Math.floor((areaBottom - areaTop - rowH * count) / 2) }
}

/** Scene frame a claim appears on the board, or null when it is introduced only after this scene. */
export function claimAppear(introducedAbs: number | undefined, index: number, sceneFrom: number, sceneEnd: number): number | null {
  if (introducedAbs === undefined) return 8 + index * 10
  if (introducedAbs >= sceneEnd) return null
  return Math.max(0, introducedAbs - sceneFrom)
}

export const ClaimBoard: React.FC<BlockProps<ClaimBoardProps>> = ({ props: p, cues, durationInFrames, sceneId, sceneFrom, stage }) => {
  const frame = useCurrentFrame()
  const { state } = useEpisode()
  const title = p.title ?? 'The claims'
  const { rowH, labelSize, top: rowsTop } = boardLayout(p.claims.length, stage.y + TITLE_H + 30, stage.y + stage.h)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: TITLE_H, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {title}
      </LayoutBox>
      {p.claims.map((c, i) => {
        const appear = claimAppear(state.introduced.get(c.id), i, sceneFrom, sceneFrom + durationInFrames)
        if (appear === null || frame < appear) return null
        const { status, since } = claimStatusAt(state, c.id, c.status, sceneFrom + frame)
        const color = statusColor[status]
        const top = rowsTop + i * rowH
        const hl = firstCue(cues, 'highlight', c.id)
        const glow = hl === null ? 0 : progress(frame, hl, 10)
        return (
          <div key={c.id} style={{ position: 'absolute', left: stage.x, top, width: stage.w, height: rowH - 14, ...bootIn(frame, appear, 14) }}>
            <div style={{ position: 'absolute', inset: 0, background: colors.bgPanel, border: `2px solid ${colors.amber}`, opacity: glow }} />
            <div style={{ position: 'absolute', left: 0, top: 0, width: 10, height: rowH - 14, background: color }} />
            <div style={{ position: 'absolute', left: 34, top: (rowH - 14 - 64) / 2 }}>
              <Icon name={c.icon} color={color} size={64} />
            </div>
            <LayoutBox id={`${sceneId}:claim:${c.id}`} kind="text" style={{ position: 'absolute', left: 120, top: 6, width: stage.w - 120 - STATUS_W, height: rowH - 26, overflow: 'hidden', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div style={{ ...body(labelSize, colors.white), lineHeight: 1.2 }}>{c.label}</div>
              {c.by ? <div style={hud(22, colors.crt400)}>{c.by}</div> : null}
            </LayoutBox>
            {since !== null ? (
              <Stamp id={`${sceneId}:stamp:${c.id}`} text={status} color={color} start={since - sceneFrom} size={32} style={{ left: stage.w - STATUS_W + 40, top: (rowH - 14 - 62) / 2 }} />
            ) : (
              <LayoutBox id={`${sceneId}:status:${c.id}`} kind="text" style={{ position: 'absolute', left: stage.w - STATUS_W + 40, top: (rowH - 14 - 34) / 2, ...hud(28, color) }}>
                {status}
              </LayoutBox>
            )}
          </div>
        )
      })}
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/Meter.tsx`** (complete file):

```tsx
/**
 * Meter: the probability meter between two hypotheses, large across the stage.
 * It starts at `start`; every meter cue of the episode, whichever scene carried
 * it, rolls the split to its value (state.ts), so a Meter shown later picks up
 * where the last one stopped. Under the numbers the house probability words.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { useEpisode } from '../context'
import { verbal } from '../format'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn } from '../motion'
import { meterAt } from '../state'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { MeterValue } from '../timeline'
import type { BlockProps } from './types'

export type MeterProps = { hypotheses: [string, string]; start: MeterValue; title?: string; note?: string }

const LABEL_H = 96
const PCT_H = 150
const WORDS_H = 40
const BAR_H = 64
const NOTE_H = 84

/** Top of the labels row: the whole stack (labels, numbers, words, bar, note) centred below the title. */
export function meterTop(stageY: number, stageH: number, withNote: boolean): number {
  const stack = LABEL_H + 10 + PCT_H + WORDS_H + 30 + BAR_H + (withNote ? 40 + NOTE_H : 0)
  const areaTop = stageY + 90
  return areaTop + Math.max(0, Math.floor((stageY + stageH - areaTop - stack) / 2))
}

export function checkMeter(p: MeterProps): string[] {
  return p.start[0] + p.start[1] === 100 ? [] : [`meter start ${JSON.stringify(p.start)} must sum to 100`]
}

export const Meter: React.FC<BlockProps<MeterProps>> = ({ props: p, sceneId, sceneFrom, stage }) => {
  const frame = useCurrentFrame()
  const { state } = useEpisode()
  const { a } = meterAt(state, p.start, sceneFrom + frame)
  const b = 100 - a
  const colW = Math.floor(stage.w / 2) - 40
  const labelsY = meterTop(stage.y, stage.h, Boolean(p.note))
  const pctY = labelsY + LABEL_H + 10
  const wordsY = pctY + PCT_H
  const barY = wordsY + WORDS_H + 30
  const noteY = barY + BAR_H + 40
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title ?? 'The balance of evidence'}
      </LayoutBox>
      {[0, 1].map((side) => {
        const value = side === 0 ? a : b
        const color = side === 0 ? colors.green : colors.amber
        const left = side === 0 ? stage.x : stage.x + stage.w - colW
        const align = side === 0 ? 'left' : 'right'
        return (
          <React.Fragment key={side}>
            <LayoutBox id={`${sceneId}:hyp${side}`} kind="text" style={{ position: 'absolute', left, top: labelsY, width: colW, height: LABEL_H, overflow: 'hidden', textAlign: align, ...body(36, colors.text), lineHeight: 1.25, ...bootIn(frame, 6 + side * 6) }}>
              {p.hypotheses[side]}
            </LayoutBox>
            <LayoutBox id={`${sceneId}:pct${side}`} kind="text" style={{ position: 'absolute', left, top: pctY, width: colW, height: PCT_H, overflow: 'hidden', textAlign: align, ...heading(110, color), letterSpacing: '0.02em', ...bootIn(frame, 10 + side * 6) }}>
              {`${Math.round(value)}%`}
            </LayoutBox>
            <LayoutBox id={`${sceneId}:words${side}`} kind="text" style={{ position: 'absolute', left, top: wordsY, width: colW, height: WORDS_H, overflow: 'hidden', textAlign: align, ...hud(26, colors.crt300), ...bootIn(frame, 14 + side * 6) }}>
              {verbal(value)}
            </LayoutBox>
          </React.Fragment>
        )
      })}
      <div style={{ position: 'absolute', left: stage.x, top: barY, width: stage.w, height: BAR_H, border: `1px solid ${colors.greenDim}`, ...bootIn(frame, 8) }}>
        <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${a}%`, background: colors.green }} />
        <div style={{ position: 'absolute', right: 0, top: 0, height: '100%', width: `${b}%`, background: colors.amber, opacity: 0.85 }} />
        <div style={{ position: 'absolute', left: `${a}%`, top: -12, width: 4, height: BAR_H + 24, marginLeft: -2, background: colors.white }} />
      </div>
      {p.note ? (
        <LayoutBox id={`${sceneId}:note`} kind="text" style={{ position: 'absolute', left: stage.x, top: noteY, width: stage.w, height: NOTE_H, overflow: 'hidden', textAlign: 'center', ...body(30, colors.white), ...bootIn(frame, 20) }}>
          {p.note}
        </LayoutBox>
      ) : null}
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/ListCard.tsx`** (complete file):

```tsx
/**
 * ListCard: a short numbered list across the stage, e.g. "what would change our
 * mind" or the verdict's reasons. Items boot in on their show <id> cues,
 * staggered otherwise; an optional note closes the card.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn } from '../motion'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { Panel } from './Panel'
import type { BlockProps } from './types'

export type ListItem = { id: string; text: string }
export type ListCardProps = { title: string; items: ListItem[]; note?: string }

const PAD = 56
const NOTE_H = 70

export const ListCard: React.FC<BlockProps<ListCardProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const panel = { x: stage.x + 60, y: stage.y + 10, w: stage.w - 120, h: stage.h - 20 }
  const listTop = PAD + 80
  const listBottom = panel.h - PAD - (p.note ? NOTE_H + 16 : 0)
  const rowH = Math.min(130, Math.floor((listBottom - listTop) / p.items.length))
  const itemSize = rowH >= 110 ? 40 : 32
  const first = listTop + Math.floor((listBottom - listTop - rowH * p.items.length) / 2)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <Panel rect={panel}>
        <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: PAD, top: PAD, width: panel.w - 2 * PAD, height: 60, overflow: 'hidden', ...heading(44), ...bootIn(frame, 4) }}>
          {p.title}
        </LayoutBox>
        {p.items.map((item, i) => {
          const appear = firstCue(cues, 'show', item.id) ?? 14 + i * 14
          if (frame < appear) return null
          return (
            <div key={item.id} style={{ position: 'absolute', left: PAD, top: first + i * rowH, width: panel.w - 2 * PAD, height: rowH - 12, ...bootIn(frame, appear, 14) }}>
              <div style={{ position: 'absolute', left: 0, top: 4, ...hud(40, colors.green) }}>{String(i + 1).padStart(2, '0')}</div>
              <LayoutBox id={`${sceneId}:item:${item.id}`} kind="text" style={{ position: 'absolute', left: 110, top: 0, width: panel.w - 2 * PAD - 110, height: rowH - 12, overflow: 'hidden', ...body(itemSize, colors.white), lineHeight: 1.25 }}>
                {item.text}
              </LayoutBox>
            </div>
          )
        })}
        {p.note ? (
          <LayoutBox id={`${sceneId}:note`} kind="text" style={{ position: 'absolute', left: PAD, top: panel.h - PAD - NOTE_H, width: panel.w - 2 * PAD, height: NOTE_H, overflow: 'hidden', ...body(26, colors.crt300), ...bootIn(frame, 30) }}>
            {p.note}
          </LayoutBox>
        ) : null}
      </Panel>
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/ShareCard.tsx`** (complete file):

```tsx
/**
 * ShareCard: the end card, the one place the link appears in the picture
 * (owner rule: platform moments are never adverts; the link is on the end
 * card and in the description only). checkBlocks (index.ts) refuses it on any
 * scene but the last.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, typeOn } from '../motion'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { Panel } from './Panel'
import type { BlockProps } from './types'

export type ShareCardProps = { headline: string; url: string; lines: string[] }

export const ShareCard: React.FC<BlockProps<ShareCardProps>> = ({ props: p, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const panel = { x: stage.x + 200, y: stage.y + 60, w: stage.w - 400, h: stage.h - 120 }
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <Panel rect={panel}>
        <LayoutBox id={`${sceneId}:headline`} kind="text" style={{ position: 'absolute', left: 64, top: 60, width: panel.w - 128, height: 130, overflow: 'hidden', ...heading(54), ...bootIn(frame, 8) }}>
          {p.headline}
        </LayoutBox>
        <LayoutBox id={`${sceneId}:url`} kind="text" style={{ position: 'absolute', left: 64, top: 220, width: panel.w - 128, height: 64, overflow: 'hidden', whiteSpace: 'nowrap', ...hud(44, colors.green), letterSpacing: '0.02em', textTransform: 'none' }}>
          {typeOn(p.url, frame, 18, 1.5)}
        </LayoutBox>
        {p.lines.map((line, i) => (
          <LayoutBox key={line} id={`${sceneId}:line${i}`} kind="text" style={{ position: 'absolute', left: 64, top: 320 + i * 50, width: panel.w - 128, height: 44, overflow: 'hidden', whiteSpace: 'nowrap', ...body(30, colors.crt300), ...bootIn(frame, 40 + i * 8) }}>
            {line}
          </LayoutBox>
        ))}
      </Panel>
    </AbsoluteFill>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/blocks-cards.test.ts`
Expected: `Tests  7 passed (7)`

- [ ] **Step 5: Commit**

```bash
git add video/src/blocks/EvidenceCard.tsx video/src/blocks/QuoteCard.tsx video/src/blocks/SourceViewer.tsx video/src/blocks/ClaimBoard.tsx video/src/blocks/Meter.tsx video/src/blocks/ListCard.tsx video/src/blocks/ShareCard.tsx video/test/blocks-cards.test.ts
git commit -m "Add the case-file cards: evidence, quote, source page, claim board, meter, list and end card" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 16: Infographics for all four topic types

**Files:**
- Create: `video/src/blocks/ScaleDrawing.tsx`, `video/src/blocks/UnitGrid.tsx`, `video/src/blocks/BarChart.tsx`, `video/src/blocks/ScaleZoom.tsx`, `video/src/blocks/Timeline.tsx`, `video/src/blocks/Diagram.tsx`
- Test: `video/test/blocks-infographics.test.ts`

Spec 4.10: type A (single site) uses ScaleDrawing (a to-scale side view: the answer to "no measuring lines on oblique photos"), UnitGrid and Timeline of phases; type B (many places) BarChart and Timeline, and the world distribution on the globe (GlobeShot over a `distribution` take, Task 31) or on the platform (PlatformClip with the `filter` and `toggle_layer` actions, Task 30); type C (science) Diagram (NERV wireframe primitives, orbits animated by the frame) and orders of magnitude as a UnitGrid up to 1:400 (it holds at most 400 cells) and a ScaleZoom beyond; type D (texts) Timeline of transmission. Every infographic is linear, never logarithmic (owner decision 31: a log scale is not pictorial and nobody reads it): BarChart has no `scale` prop, and ScaleZoom is the Powers-of-Ten idea without a log axis. It draws the two quantities as bars on one linear scale from the same left edge; the small one first fills 80 % of the bar area, then from 25 % of the scene the camera pulls back linearly (the visible extent grows linearly from the small value to the large one, eased at both ends) until, one second before the scene ends, the large one fills 80 %, and the small one shrinks to a dot that keeps its label and value. Every frame is a pure function of the frame number, and in every frame the two bars stand in the ratio of their values (tested). A linear pull on a large ratio shrinks the small bar to a dot within the first frames of the pull-back (measured on the demo render, 1:6,000): the readable phase is the time before the pull-back, the dot and its label keep the small quantity visible afterwards. This is recorded as owner question Q6 (`2026-09-26-owner-questions.md`, "Open", and the build index's section 8); until the owner answers, the build keeps the linear pull-back exactly as decision 31 words it (`zoomScale` unchanged). A BarChart value is a number or `[low, high]`: spec 4.2 wants a quantity with a range to show the range, so the bar is solid to `low`, outlined on to `high` and labelled `low–high unit`. Every value is printed with the decimals it is written with (`decimalsOf` counts the exact decimals of the number's shortest form, exponent form included, with no cap: 1.75 stays 1.75, never 1.8, and 1.5e-7 prints 0.00000015, never 0), because a bar or ScaleZoom quantity whose id is a case-file quantity id must show exactly that quantity (plan C checks its value and the chart's `unit`). A value too long for its box then fails the layout lint as `overflow`; it is never printed as another number. Every comparison block prints its basis on screen through its exported `basisLine(props)`.

- [ ] **Step 1: Write the failing test**

**`video/test/blocks-infographics.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { type BarChartProps, barAxis, barFraction, basisLine as barBasis, checkBarChart, valueText } from '../src/blocks/BarChart'
import { checkDiagram, fitDiagram } from '../src/blocks/Diagram'
import { basisLine as scaleBasis, checkScaleDrawing, dimensionLabel, fitScale } from '../src/blocks/ScaleDrawing'
import { DOT, FILL, MIN_FRAMES, type ScaleZoomProps, checkScaleZoom, pullWindow, basisLine as zoomBasis, zoomScale } from '../src/blocks/ScaleZoom'
import { checkTimeline, labelAnchor } from '../src/blocks/Timeline'
import { checkUnitGrid, basisLine as gridBasis, gridLayout, groupStarts } from '../src/blocks/UnitGrid'

describe('ScaleDrawing', () => {
  const objects = [
    { id: 'o1', label: 'Stone', shape: 'block' as const, width: 20, height: 6, x: 0 },
    { id: 'o2', label: 'Person', shape: 'person' as const, width: 0.5, height: 1.75, x: 21.5 },
  ]
  it('fits the widest extent and the tallest object at one scale', () => {
    expect(fitScale(objects, 1100, 300)).toBeCloseTo(50)
  })
  it('labels upright shapes by height and the others by width x height', () => {
    expect(dimensionLabel(objects[1], 'm')).toBe('1.75 m')
    expect(dimensionLabel(objects[0], 'm')).toBe('20 × 6 m')
  })
  it('refuses objects without a size', () => {
    expect(checkScaleDrawing({ title: 't', unit: 'm', basis: 'bus 12 m', objects: [{ ...objects[0], width: 0 }, objects[1]] })).toEqual(['object o1 needs a positive width and height'])
  })
})

describe('UnitGrid', () => {
  const groups = [
    { id: 'a', count: 40, label: 'a', tone: 'accent' as const },
    { id: 'b', count: 10, label: 'b', tone: 'warn' as const },
  ]
  it('starts each group after the previous one filled, or on its show cue', () => {
    expect(groupStarts(groups, () => null)).toEqual([12, 38])
    expect(groupStarts(groups, (id) => (id === 'b' ? 100 : null))).toEqual([12, 100])
  })
  it('picks the largest cells, or the given columns', () => {
    expect(gridLayout(80, { x: 0, y: 0, w: 1100, h: 500 })).toEqual({ columns: 14, rows: 6, cell: 1100 / 14 })
    expect(gridLayout(80, { x: 0, y: 0, w: 1100, h: 500 }, 20).columns).toBe(20)
  })
  it('holds at most 400 cells', () => {
    expect(checkUnitGrid({ title: 't', basis: 'b', unitLabel: 'u', groups: [{ id: 'a', count: 401, label: 'a', tone: 'accent' }] })).toEqual(['401 cells; the grid holds at most 400'])
  })
})

describe('BarChart', () => {
  it('needs something to compare', () => {
    expect(checkBarChart({ title: 't', unit: 't', basis: 'b', bars: [{ id: 'x', label: 'x', value: 0 }, { id: 'y', label: 'y', value: 0 }] })).toEqual(['every bar is 0: nothing to compare'])
  })
  it('shows a range where sources differ and refuses an empty range', () => {
    const p: BarChartProps = { title: 't', unit: 't', basis: 'b', bars: [{ id: 'x', label: 'x', value: [1000, 1650] }, { id: 'y', label: 'y', value: 500 }] }
    expect(checkBarChart(p)).toEqual([])
    const axis = barAxis(p)
    expect(axis).toEqual({ lo: 0, hi: 1650 })
    expect(barFraction(axis, 1000)).toBeCloseTo(1000 / 1650)
    expect(valueText([1000, 1650], 't')).toBe('1,000–1,650 t')
    expect(valueText(12.5, 't')).toBe('12.5 t')
    // a bar bound to a case-file quantity shows exactly its value: 1.75 stays 1.75, not 1.8
    expect(valueText(1.75, 'm')).toBe('1.75 m')
    const empty: BarChartProps = { ...p, bars: [{ id: 'x', label: 'x', value: [1650, 1000] }, p.bars[1]] }
    expect(checkBarChart(empty)).toEqual(['bar x: range [1650, 1000] needs low < high'])
  })
  it('prints small values exactly, exponent form included, never rounded to another number', () => {
    expect(valueText(1.5e-7, 'm')).toBe('0.00000015 m')
    expect(valueText(0.0000015, 'm')).toBe('0.0000015 m')
    expect(valueText(1e-10, 'm')).toBe('0.0000000001 m')
  })
})

describe('ScaleZoom (owner decision 31: linear, never a log axis)', () => {
  const p: ScaleZoomProps = {
    title: 't',
    unit: 'km',
    basis: 'b',
    small: { id: 'q1', label: 'Earth', value: 12742 },
    large: { id: 'q2', label: 'Sun', value: 1392700 },
  }
  it('pulls back from the small quantity to the large one over the middle of the scene', () => {
    expect(pullWindow(300)).toEqual({ start: 75, end: 240 })
    expect(p.small.value * zoomScale(p, 1600, 0, 300)).toBeCloseTo(FILL * 1600)
    expect(p.large.value * zoomScale(p, 1600, 299, 300)).toBeCloseTo(FILL * 1600)
    // the small one ends as a dot: far below DOT pixels on the fitted scale
    expect(p.small.value * zoomScale(p, 1600, 299, 300)).toBeLessThan(DOT)
  })
  it('draws both quantities on one linear scale in every frame', () => {
    for (const frame of [0, 80, 120, 160, 200, 240, 299]) {
      const s = zoomScale(p, 1600, frame, 300)
      expect((p.small.value * s) / (p.large.value * s)).toBeCloseTo(p.small.value / p.large.value, 12)
    }
    // the visible extent grows linearly between the eased ends: halfway through the pull it is halfway between the two values
    const { start, end } = pullWindow(300)
    expect((FILL * 1600) / zoomScale(p, 1600, (start + end) / 2, 300)).toBeCloseTo((p.small.value + p.large.value) / 2, 3)
  })
  it('refuses a small value of 0, a large value not above it and a scene too short for the pull-back', () => {
    expect(checkScaleZoom(p, { fps: 60, durationInFrames: MIN_FRAMES })).toEqual([])
    expect(checkScaleZoom({ ...p, small: { ...p.small, value: 0 } }, { fps: 60, durationInFrames: 300 })).toEqual(['q1: the small value must be greater than 0'])
    expect(checkScaleZoom({ ...p, large: { ...p.large, value: 12742 } }, { fps: 60, durationInFrames: 300 })).toEqual(['q2: the large value 12742 must be greater than the small value 12742'])
    expect(checkScaleZoom(p, { fps: 60, durationInFrames: 180 })).toEqual([
      'a ScaleZoom scene needs at least 240 frames (the small quantity, the pull-back, a 1 s hold), got 180',
    ])
  })
})

describe('basis lines (owner rule: comparisons state their basis)', () => {
  it('print the basis verbatim on screen', () => {
    const basis = 'block 20.5 m x 4 m, DAI 2014; person 1.75 m'
    expect(scaleBasis({ title: 't', unit: 'm', basis, objects: [] })).toBe(`To scale. Basis: ${basis}`)
    expect(gridBasis({ title: 't', basis, unitLabel: 'one city bus', groups: [] })).toBe(`1 square = one city bus. Basis: ${basis}`)
    expect(barBasis({ title: 't', unit: 't', basis, bars: [] })).toBe(`Basis: ${basis}`)
    const q = { id: 'q', label: 'q', value: 1 }
    expect(zoomBasis({ title: 't', unit: 'km', basis, small: q, large: { ...q, id: 'r', value: 1000 } })).toBe(`To scale, linear. Basis: ${basis}`)
  })
})

describe('Timeline', () => {
  it('aligns labels near the ends to the edge', () => {
    expect(labelAnchor(0.05).textAlign).toBe('left')
    expect(labelAnchor(0.5).textAlign).toBe('center')
    expect(labelAnchor(0.95).textAlign).toBe('right')
  })
  it('refuses an empty range, events outside it and year 0', () => {
    expect(checkTimeline({ title: 't', from: 100, to: 100, events: [] })).toEqual(['timeline range 100..100 is empty'])
    expect(checkTimeline({ title: 't', from: -100, to: 100, events: [{ id: 'e', year: 0, label: 'x', tone: 'muted' }] })).toEqual(['event e: year 0 does not exist'])
    expect(checkTimeline({ title: 't', from: -100, to: 100, events: [{ id: 'e', year: 300, label: 'x', tone: 'muted' }] })).toEqual(['event e (300) lies outside -100..100'])
  })
})

describe('Diagram', () => {
  it('centres the user space in the drawing area at one scale', () => {
    expect(fitDiagram(100, 50, { x: 0, y: 0, w: 1000, h: 1000 })).toEqual({ s: 10, ox: 0, oy: 250 })
  })
  it('needs the geometry of each element type', () => {
    expect(checkDiagram({ title: 't', width: 10, height: 10, elements: [{ id: 'd2', type: 'circle', tone: 'accent', cx: 1, cy: 1 }] })).toEqual(['element d2 (circle) needs "r"'])
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/blocks-infographics.test.ts`
Expected: FAIL with `Cannot find module '../src/blocks/BarChart'`.

- [ ] **Step 3: Implement**

**`video/src/blocks/ScaleDrawing.tsx`** (complete file):

```tsx
/**
 * ScaleDrawing: a to-scale side view of 2-5 objects on one ground line, all at
 * the same metres per pixel, with their dimensions labelled and the basis always
 * on screen ("block 20.5 m long, DAI 2014; person 1.75 m"): comparisons state
 * their basis, and lengths are never drawn on oblique photos (owner rules).
 * Objects grow in on their show <id> cues, staggered otherwise.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { formatNumber } from '../format'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps } from './types'

export type ScaleShape = 'block' | 'person' | 'column' | 'bus' | 'pyramid' | 'rect'
export type ScaleObject = { id: string; label: string; shape: ScaleShape; width: number; height: number; x: number }
export type ScaleDrawingProps = { title: string; unit: 'cm' | 'm' | 'km'; basis: string; objects: ScaleObject[] }

const LABEL_ROOM = 90
const BASIS_H = 56
const PALETTE = [colors.green, colors.amber, colors.cyan, colors.crt300, colors.orange]

/** Pixels per unit so the widest extent and the tallest object both fit the drawing area. */
export function fitScale(objects: readonly ScaleObject[], w: number, h: number): number {
  const extent = Math.max(...objects.map((o) => o.x + o.width))
  const tallest = Math.max(...objects.map((o) => o.height))
  return Math.min(w / extent, h / tallest)
}

export function drawArea(stage: Rect): Rect {
  const top = stage.y + 60 + LABEL_ROOM
  return { x: stage.x + 60, y: top, w: stage.w - 120, h: stage.y + stage.h - BASIS_H - 20 - top }
}

/** The ground line: the drawing (tallest object on it) centred vertically in the area. */
export function groundLine(objects: readonly ScaleObject[], s: number, area: Rect): number {
  const tallest = Math.max(...objects.map((o) => o.height)) * s
  return area.y + Math.round((area.h + tallest) / 2)
}

/** The dimension label: the height of upright shapes, width x height of the others. */
export function dimensionLabel(o: ScaleObject, unit: string): string {
  const upright = o.shape === 'person' || o.shape === 'column' || o.shape === 'pyramid'
  return upright ? `${formatNumber(o.height, 2)} ${unit}` : `${formatNumber(o.width, 2)} × ${formatNumber(o.height, 2)} ${unit}`
}

export function checkScaleDrawing(p: ScaleDrawingProps): string[] {
  return p.objects.filter((o) => o.width <= 0 || o.height <= 0).map((o) => `object ${o.id} needs a positive width and height`)
}

/** The on-screen basis line (owner rule: comparisons state their basis). */
export function basisLine(p: ScaleDrawingProps): string {
  return `To scale. Basis: ${p.basis}`
}

function shapePath(o: ScaleObject, x: number, ground: number, w: number, h: number): React.ReactNode {
  const top = ground - h
  switch (o.shape) {
    case 'person': {
      const head = Math.min(w, h * 0.13)
      return (
        <g>
          <circle cx={x + w / 2} cy={top + head / 2} r={head / 2} />
          <path d={`M${x + w / 2} ${top + head} V${ground - h * 0.45} M${x} ${top + h * 0.32} H${x + w} M${x + w / 2} ${ground - h * 0.45} L${x + w * 0.1} ${ground} M${x + w / 2} ${ground - h * 0.45} L${x + w * 0.9} ${ground}`} />
        </g>
      )
    }
    case 'column':
      return <path d={`M${x} ${ground} V${top + h * 0.06} H${x + w} V${ground} M${x - w * 0.15} ${top} H${x + w * 1.15} V${top + h * 0.06} H${x - w * 0.15} Z`} />
    case 'pyramid':
      return <path d={`M${x} ${ground} L${x + w / 2} ${top} L${x + w} ${ground} Z`} />
    case 'bus':
      return (
        <g>
          <rect x={x} y={top} width={w} height={h * 0.82} rx={h * 0.08} />
          <circle cx={x + w * 0.2} cy={ground - h * 0.1} r={h * 0.1} />
          <circle cx={x + w * 0.8} cy={ground - h * 0.1} r={h * 0.1} />
        </g>
      )
    case 'block':
    case 'rect':
      return <rect x={x} y={top} width={w} height={h} />
  }
}

export const ScaleDrawing: React.FC<BlockProps<ScaleDrawingProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const area = drawArea(stage)
  const s = fitScale(p.objects, area.w, area.h)
  const ground = groundLine(p.objects, s, area)
  const appear = p.objects.map((o, i) => firstCue(cues, 'show', o.id) ?? 10 + i * 18)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <line x1={area.x} y1={ground} x2={area.x + area.w} y2={ground} stroke={colors.greenDim} strokeWidth={3} />
        {p.objects.map((o, i) => {
          const grow = progress(frame, appear[i], 22)
          if (grow <= 0) return null
          const color = PALETTE[i % PALETTE.length]
          return (
            <g key={o.id} fill={`${color}33`} stroke={color} strokeWidth={3}>
              {shapePath(o, area.x + o.x * s, ground, o.width * s, o.height * s * grow)}
            </g>
          )
        })}
      </svg>
      {p.objects.map((o, i) => {
        if (frame < appear[i] + 16) return null
        const top = Math.max(stage.y + 70, ground - o.height * s - LABEL_ROOM + 6)
        return (
          <LayoutBox
            key={o.id}
            id={`${sceneId}:obj:${o.id}`}
            kind="text"
            style={{ position: 'absolute', left: area.x + (o.x + o.width / 2) * s, top, textAlign: 'center', whiteSpace: 'nowrap', ...bootIn(frame, appear[i] + 16, 12, 'translateX(-50%)') }}
          >
            <div style={hud(24, colors.crt300)}>{o.label}</div>
            <div style={hud(32, colors.white)}>{dimensionLabel(o, p.unit)}</div>
          </LayoutBox>
        )
      })}
      <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
        {basisLine(p)}
      </LayoutBox>
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/UnitGrid.tsx`** (complete file):

```tsx
/**
 * UnitGrid: counts as unit squares ("one block = 80 city buses"), at most 400
 * cells, as large as the stage allows (ratios beyond 1:400 are a ScaleZoom,
 * linear too: owner decision 31). Groups light up one after the
 * other (a group starts on its show <id> cue, otherwise when the previous one
 * has filled) while their numbers roll; the basis is always on screen.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, digitRoll } from '../motion'
import { type Tone, colors, toneColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps } from './types'

export type UnitGroup = { id: string; count: number; label: string; tone: Tone }
export type UnitGridProps = { title: string; basis: string; unitLabel: string; columns?: number; groups: UnitGroup[] }

const MAX_CELLS = 400
/** Cells lit per frame while a group fills. */
const FILL_RATE = 2
const LEGEND_W = 480
const BASIS_H = 56

export function checkUnitGrid(p: UnitGridProps): string[] {
  const total = p.groups.reduce((n, g) => n + g.count, 0)
  return total > MAX_CELLS ? [`${total} cells; the grid holds at most ${MAX_CELLS}`] : []
}

/** The on-screen basis line (owner rule: comparisons state their basis). */
export function basisLine(p: UnitGridProps): string {
  return `1 square = ${p.unitLabel}. Basis: ${p.basis}`
}

/** First frame of each group: its show cue, else when the previous group has filled. */
export function groupStarts(groups: readonly UnitGroup[], cueFrame: (id: string) => number | null, first = 12): number[] {
  const starts: number[] = []
  groups.forEach((g, i) => {
    const prevEnd = i === 0 ? first : starts[i - 1] + Math.ceil(groups[i - 1].count / FILL_RATE) + 6
    starts.push(cueFrame(g.id) ?? prevEnd)
  })
  return starts
}

/** Grid geometry: columns (given, or the count that makes the cells largest) and the cell size. */
export function gridLayout(total: number, area: Rect, columns?: number): { columns: number; rows: number; cell: number } {
  const candidates = columns !== undefined ? [columns] : Array.from({ length: Math.min(total, 40) }, (_, i) => i + 1)
  let best = { columns: 1, rows: total, cell: 0 }
  for (const c of candidates) {
    const rows = Math.ceil(total / c)
    const cell = Math.min(area.w / c, area.h / rows)
    if (cell > best.cell) best = { columns: c, rows, cell }
  }
  return best
}

export const UnitGrid: React.FC<BlockProps<UnitGridProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const starts = groupStarts(p.groups, (id) => firstCue(cues, 'show', id))
  const total = p.groups.reduce((n, g) => n + g.count, 0)
  const area = { x: stage.x, y: stage.y + 90, w: stage.w - LEGEND_W - 60, h: stage.h - 90 - BASIS_H - 30 }
  const { columns, cell } = gridLayout(total, area, p.columns)
  const gap = Math.max(2, cell * 0.14)
  const cells: React.ReactNode[] = []
  let index = 0
  p.groups.forEach((g, gi) => {
    const lit = Math.max(0, Math.min(g.count, Math.floor((frame - starts[gi]) * FILL_RATE)))
    for (let k = 0; k < g.count; k++, index++) {
      const on = k < lit
      cells.push(
        <div
          key={index}
          style={{
            position: 'absolute',
            left: (index % columns) * cell,
            top: Math.floor(index / columns) * cell,
            width: cell - gap,
            height: cell - gap,
            background: on ? toneColor[g.tone] : 'transparent',
            border: `1px solid ${on ? toneColor[g.tone] : colors.greenDim}`,
          }}
        />,
      )
    }
  })
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <div style={{ position: 'absolute', left: area.x, top: area.y, width: area.w, height: area.h }}>{cells}</div>
      <div style={{ position: 'absolute', left: stage.x + stage.w - LEGEND_W, top: area.y, width: LEGEND_W }}>
        {p.groups.map((g, gi) => {
          if (frame < starts[gi]) return null
          return (
            <LayoutBox key={g.id} id={`${sceneId}:group:${g.id}`} kind="text" style={{ marginBottom: 32, ...bootIn(frame, starts[gi], 12) }}>
              <div style={{ ...hud(72, toneColor[g.tone]), letterSpacing: '0.02em' }}>{digitRoll(0, g.count, frame, starts[gi], Math.ceil(g.count / FILL_RATE))}</div>
              <div style={body(30, colors.text)}>{g.label}</div>
            </LayoutBox>
          )
        })}
      </div>
      <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
        {basisLine(p)}
      </LayoutBox>
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/BarChart.tsx`** (complete file):

```tsx
/**
 * BarChart: horizontal bars on a linear axis for frequencies and sizes (type B:
 * how many sites per region, per period). Linear only (owner decision 31: a
 * log axis is not pictorial; ratios beyond a UnitGrid's 1:400 are a ScaleZoom).
 * A value is a number, or [low, high] when sources differ: the bar is solid to
 * low and outlined on to high, labelled "low–high unit" (spec 4.2: a quantity
 * with a range shows the range). Bars grow in on their show <id> cues,
 * staggered otherwise; a single value rolls with its bar; the basis is always
 * on screen.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { formatNumber } from '../format'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { type Tone, colors, toneColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps } from './types'

export type BarValue = number | [number, number]
export type Bar = { id: string; label: string; value: BarValue; tone?: Tone }
export type BarChartProps = { title: string; unit: string; basis: string; bars: Bar[] }
/** The linear value axis 0..hi. */
export type BarAxis = { lo: 0; hi: number }

const LABEL_W = 580
const VALUE_W = 360
const BASIS_H = 56
const GROW_FRAMES = 30

const lowOf = (v: BarValue): number => (Array.isArray(v) ? v[0] : v)
const highOf = (v: BarValue): number => (Array.isArray(v) ? v[1] : v)
/**
 * The exact decimals of `x`'s shortest form, exponent form included, with no cap (1.75 -> 2,
 * 1.5e-7 -> 8, 1e21 -> 0), so a value bound to a case-file quantity prints exactly that value;
 * one too long for its box fails the layout lint as `overflow`, never prints as another number.
 */
const decimalsOf = (x: number): number => {
  const [mantissa, exp = '0'] = String(x).split('e')
  return Math.max(0, (mantissa.split('.')[1] ?? '').length - Number(exp))
}

export function checkBarChart(p: BarChartProps): string[] {
  const errors: string[] = []
  for (const b of p.bars) {
    if (Array.isArray(b.value) && !(b.value[0] < b.value[1])) errors.push(`bar ${b.id}: range [${b.value[0]}, ${b.value[1]}] needs low < high`)
  }
  if (!p.bars.some((b) => highOf(b.value) > 0)) errors.push('every bar is 0: nothing to compare')
  return errors
}

/** The axis of the chart: 0 up to the largest (high) value. */
export function barAxis(p: BarChartProps): BarAxis {
  return { lo: 0, hi: Math.max(...p.bars.map((b) => highOf(b.value))) }
}

/** Where `value` lies along the bar area, 0..1 (linear). */
export function barFraction(axis: BarAxis, value: number): number {
  return value / axis.hi
}

/** "1,250 t", "1.75 m", or "1,000–1,650 t" for a range; every value keeps its own decimals. */
export function valueText(v: BarValue, unit: string): string {
  const n = (x: number) => formatNumber(x, decimalsOf(x))
  return `${Array.isArray(v) ? `${n(v[0])}–${n(v[1])}` : n(v)} ${unit}`
}

/** The on-screen basis line (owner rule: comparisons state their basis). */
export function basisLine(p: BarChartProps): string {
  return `Basis: ${p.basis}`
}

export const BarChart: React.FC<BlockProps<BarChartProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const axis = barAxis(p)
  const areaTop = stage.y + 100
  const areaH = stage.h - 100 - BASIS_H - 30
  const rowH = Math.min(130, Math.floor(areaH / p.bars.length))
  const top = areaTop + Math.floor((areaH - rowH * p.bars.length) / 2)
  const barX = stage.x + LABEL_W
  const barMax = stage.w - LABEL_W - VALUE_W - 40
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      {p.bars.map((b, i) => {
        const appear = firstCue(cues, 'show', b.id) ?? 12 + i * 12
        if (frame < appear) return null
        const grow = progress(frame, appear, GROW_FRAMES)
        const y = top + i * rowH
        const color = toneColor[b.tone ?? 'accent']
        const range = Array.isArray(b.value)
        const solid = barMax * barFraction(axis, lowOf(b.value)) * grow
        const end = barMax * barFraction(axis, highOf(b.value)) * grow
        // A single value rolls with its bar; a range appears once the bar has grown.
        const rolls = !range
        return (
          <React.Fragment key={b.id}>
            <LayoutBox id={`${sceneId}:bar:${b.id}`} kind="text" style={{ position: 'absolute', left: stage.x, top: y, width: LABEL_W - 20, height: rowH - 16, overflow: 'hidden', textAlign: 'right', ...body(28, colors.text), lineHeight: `${rowH - 16}px`, whiteSpace: 'nowrap', ...bootIn(frame, appear, 12) }}>
              {b.label}
            </LayoutBox>
            <div style={{ position: 'absolute', left: barX, top: y + 6, width: solid, height: rowH - 28, background: color }} />
            {range ? <div style={{ position: 'absolute', left: barX + solid, top: y + 6, width: end - solid, height: rowH - 28, boxSizing: 'border-box', border: `3px solid ${color}`, borderLeft: 'none' }} /> : null}
            <LayoutBox
              id={`${sceneId}:value:${b.id}`}
              kind="text"
              style={{ position: 'absolute', left: barX + end + 16, top: y, width: VALUE_W, height: rowH - 16, overflow: 'hidden', whiteSpace: 'nowrap', ...hud(range ? 30 : 34, colors.white), lineHeight: `${rowH - 16}px`, ...(rolls ? {} : bootIn(frame, appear + GROW_FRAMES, 12)) }}
            >
              {rolls ? `${formatNumber(lowOf(b.value) * grow, decimalsOf(lowOf(b.value)))} ${p.unit}` : valueText(b.value, p.unit)}
            </LayoutBox>
          </React.Fragment>
        )
      })}
      <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
        {basisLine(p)}
      </LayoutBox>
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/ScaleZoom.tsx`** (complete file):

```tsx
/**
 * ScaleZoom (type C, owner decision 31): the Powers-of-Ten zoom-out without a
 * log axis, for ratios a UnitGrid cannot hold (beyond 1:400). The two
 * quantities are bars on one linear scale, both starting at the same left
 * edge: first the small one fills most of the bar area (readable), then the
 * camera pulls back linearly (the visible extent grows linearly from the small
 * value to the large one, eased at both ends) until the large one fits, and
 * the small one shrinks to a dot that keeps its label. Every frame is one
 * linear scale, so the two bars always stand in the ratio of their values.
 * The pull-back runs from 25 % of the scene to one second before its end,
 * frame by frame; show <small id> and show <large id> let a quantity appear
 * (default: the small at frame 12, the large when the pull-back starts). The
 * basis is always on screen.
 */
import React from 'react'
import { AbsoluteFill, Easing, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { valueText } from './BarChart'
import type { BlockProps, CheckContext } from './types'

export type ZoomQuantity = { id: string; label: string; value: number }
export type ScaleZoomProps = { title: string; unit: string; basis: string; small: ZoomQuantity; large: ZoomQuantity }

/** The fitted quantity spans this share of the bar area's width. */
export const FILL = 0.8
/** A bar shorter than this is drawn as a dot of this diameter. */
export const DOT = 14
/** The fitted final view holds for one second at 60 fps. */
const HOLD_FRAMES = 60
/** Frames the scene needs: the small quantity, the pull-back and the hold (4 s). */
export const MIN_FRAMES = 240
const BASIS_H = 56
const LABEL_H = 48
const BAR_H = 72
const ROW_H = 170

export function checkScaleZoom(p: ScaleZoomProps, ctx: CheckContext): string[] {
  const errors: string[] = []
  if (p.small.id === p.large.id) errors.push(`small and large need different ids (both ${p.small.id})`)
  if (!(p.small.value > 0)) errors.push(`${p.small.id}: the small value must be greater than 0`)
  if (!(p.large.value > p.small.value)) errors.push(`${p.large.id}: the large value ${p.large.value} must be greater than the small value ${p.small.value}`)
  if (ctx.durationInFrames < MIN_FRAMES) {
    errors.push(`a ScaleZoom scene needs at least ${MIN_FRAMES} frames (the small quantity, the pull-back, a 1 s hold), got ${ctx.durationInFrames}`)
  }
  return errors
}

/** The frames of the pull-back: from 25 % of the scene to one second before its end. */
export function pullWindow(durationInFrames: number): { start: number; end: number } {
  return { start: Math.round(durationInFrames * 0.25), end: durationInFrames - HOLD_FRAMES }
}

/**
 * Pixels per unit at scene frame `frame` for a bar area `width` px wide: the
 * visible extent (the value that spans FILL of the width) runs linearly from
 * the small value to the large one over the pull-back, eased at both ends.
 */
export function zoomScale(p: ScaleZoomProps, width: number, frame: number, durationInFrames: number): number {
  const { start, end } = pullWindow(durationInFrames)
  const u = progress(frame, start, end - start, Easing.inOut(Easing.quad))
  const extent = p.small.value + (p.large.value - p.small.value) * u
  return (FILL * width) / extent
}

/** The on-screen basis line (owner rule: comparisons state their basis). */
export function basisLine(p: ScaleZoomProps): string {
  return `To scale, linear. Basis: ${p.basis}`
}

function barArea(stage: Rect): Rect {
  return { x: stage.x + 20, y: stage.y + 100, w: stage.w - 40, h: 2 * ROW_H }
}

export const ScaleZoom: React.FC<BlockProps<ScaleZoomProps>> = ({ props: p, cues, durationInFrames, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const area = barArea(stage)
  const s = zoomScale(p, area.w, frame, durationInFrames)
  const rows = [
    { q: p.small, appear: firstCue(cues, 'show', p.small.id) ?? 12, color: colors.amber },
    { q: p.large, appear: firstCue(cues, 'show', p.large.id) ?? pullWindow(durationInFrames).start, color: colors.green },
  ]
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <div style={{ position: 'absolute', left: area.x, top: area.y, width: area.w, height: area.h, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: 0, top: 0, width: 2, height: area.h, background: colors.greenDim }} />
        {rows.map(({ q, appear, color }, i) => {
          if (frame < appear) return null
          const length = q.value * s
          const top = i * ROW_H + LABEL_H + 12
          return length >= DOT ? (
            <div key={q.id} style={{ position: 'absolute', left: 0, top, width: length, height: BAR_H, background: color, opacity: progress(frame, appear, 12) }} />
          ) : (
            <div key={q.id} style={{ position: 'absolute', left: 0, top: top + (BAR_H - DOT) / 2, width: DOT, height: DOT, borderRadius: DOT / 2, background: color, boxShadow: `0 0 10px ${color}` }} />
          )
        })}
      </div>
      {rows.map(({ q, appear, color }, i) =>
        frame < appear ? null : (
          <LayoutBox
            key={q.id}
            id={`${sceneId}:q:${q.id}`}
            kind="text"
            style={{ position: 'absolute', left: area.x, top: area.y + i * ROW_H, width: area.w, height: LABEL_H, overflow: 'hidden', whiteSpace: 'nowrap', display: 'flex', alignItems: 'baseline', gap: 24, ...bootIn(frame, appear, 12) }}
          >
            <span style={body(32, colors.white)}>{q.label}</span>
            <span style={hud(30, color)}>{valueText(q.value, p.unit)}</span>
          </LayoutBox>
        ),
      )}
      <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
        {basisLine(p)}
      </LayoutBox>
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/Timeline.tsx`** (complete file):

```tsx
/**
 * Timeline (type D transmission, site phases): a horizontal year axis across
 * the stage. Events enter on their show <id> cues (staggered otherwise) with
 * labels alternating above and below the axis so neighbours keep apart (the
 * lint pass checks it). Negative years are BCE; year 0 does not exist.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { formatYear, yearTicks } from '../format'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { type Tone, colors, toneColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps } from './types'

export type TimelineEvent = { id: string; year: number; label: string; tone: Tone }
export type TimelineProps = { title: string; from: number; to: number; events: TimelineEvent[]; basis?: string }

const BASIS_H = 56
/** Events in the outer 15 % of the axis carry edge-aligned labels, so the label stays on screen. */
const EDGE = 0.15

/** Horizontal placement of an event label at axis fraction f: centred, or aligned to the near edge. */
export function labelAnchor(f: number): { textAlign: 'left' | 'center' | 'right'; transform: string; dx: number } {
  if (f < EDGE) return { textAlign: 'left', transform: '', dx: -16 }
  if (f > 1 - EDGE) return { textAlign: 'right', transform: 'translateX(-100%)', dx: 16 }
  return { textAlign: 'center', transform: 'translateX(-50%)', dx: 0 }
}

export function checkTimeline(p: TimelineProps): string[] {
  const errors = p.to <= p.from ? [`timeline range ${p.from}..${p.to} is empty`] : []
  for (const e of p.events) {
    if (e.year < p.from || e.year > p.to) errors.push(`event ${e.id} (${e.year}) lies outside ${p.from}..${p.to}`)
    if (e.year === 0) errors.push(`event ${e.id}: year 0 does not exist`)
  }
  return errors
}

export const Timeline: React.FC<BlockProps<TimelineProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const axis = { x: stage.x + 60, y: stage.y + Math.round((stage.h - BASIS_H) / 2) + 40, w: stage.w - 120 }
  const xOf = (year: number) => axis.x + ((year - p.from) / (p.to - p.from)) * axis.w
  const events = [...p.events].sort((a, b) => a.year - b.year)
  const drawn = progress(frame, 4, 30)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <div style={{ position: 'absolute', left: axis.x, top: axis.y, width: axis.w * drawn, height: 4, background: colors.green }} />
      {yearTicks(p.from, p.to).map((y) => (
        <div key={y} style={{ position: 'absolute', left: xOf(y), top: axis.y + 14, transform: 'translateX(-50%)', ...hud(18, colors.crt400), whiteSpace: 'nowrap', opacity: drawn }}>
          {formatYear(y)}
        </div>
      ))}
      {events.map((e, i) => {
        const appear = firstCue(cues, 'show', e.id) ?? 30 + i * 14
        if (frame < appear) return null
        const x = xOf(e.year)
        const anchor = labelAnchor((e.year - p.from) / (p.to - p.from))
        const above = i % 2 === 0
        const color = toneColor[e.tone]
        return (
          <React.Fragment key={e.id}>
            <div style={{ position: 'absolute', left: x - 11, top: axis.y - 9, width: 22, height: 22, borderRadius: 11, background: color, ...bootIn(frame, appear, 8) }} />
            <div style={{ position: 'absolute', left: x - 1, top: above ? axis.y - 80 : axis.y + 50, width: 2, height: 36, background: color, opacity: 0.7 }} />
            <LayoutBox
              id={`${sceneId}:event:${e.id}`}
              kind="text"
              style={{ position: 'absolute', left: x + anchor.dx, top: above ? axis.y - 170 : axis.y + 94, textAlign: anchor.textAlign, whiteSpace: 'nowrap', ...bootIn(frame, appear + 4, 12, anchor.transform) }}
            >
              <div style={hud(26, color)}>{formatYear(e.year)}</div>
              <div style={body(30, colors.white)}>{e.label}</div>
            </LayoutBox>
          </React.Fragment>
        )
      })}
      {p.basis ? (
        <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
          {`Dates: ${p.basis}`}
        </LayoutBox>
      ) : null}
    </AbsoluteFill>
  )
}
```

**`video/src/blocks/Diagram.tsx`** (complete file):

```tsx
/**
 * Diagram (type C, science and space): NERV wireframe primitives in a width x
 * height user space, scaled uniformly into the stage: circle, line, arrow,
 * curve (polyline through points), orbit (a body on an ellipse, one revolution
 * per `period` seconds) and label. Elements trace in on their show <id> cues,
 * staggered otherwise. Schematic: the basis line says what it simplifies.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { firstCue } from '../cues'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { type Tone, colors, toneColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps } from './types'

export type DiagramElement = {
  id: string
  type: 'circle' | 'line' | 'arrow' | 'curve' | 'orbit' | 'label'
  tone: Tone
  label?: string
  cx?: number
  cy?: number
  r?: number
  rx?: number
  ry?: number
  period?: number
  x1?: number
  y1?: number
  x2?: number
  y2?: number
  dashed?: boolean
  points?: [number, number][]
  x?: number
  y?: number
  text?: string
}
export type DiagramProps = { title: string; width: number; height: number; basis?: string; elements: DiagramElement[] }

const BASIS_H = 56

const REQUIRED: Record<DiagramElement['type'], (keyof DiagramElement)[]> = {
  circle: ['cx', 'cy', 'r'],
  line: ['x1', 'y1', 'x2', 'y2'],
  arrow: ['x1', 'y1', 'x2', 'y2'],
  curve: ['points'],
  orbit: ['cx', 'cy', 'rx', 'ry', 'period'],
  label: ['x', 'y', 'text'],
}

export function checkDiagram(p: DiagramProps): string[] {
  const errors: string[] = []
  for (const e of p.elements) {
    for (const key of REQUIRED[e.type]) if (e[key] === undefined) errors.push(`element ${e.id} (${e.type}) needs "${key}"`)
  }
  return errors
}

/** Uniform scale and offset placing the user space in the drawing area, centred. */
export function fitDiagram(width: number, height: number, area: Rect): { s: number; ox: number; oy: number } {
  const s = Math.min(area.w / width, area.h / height)
  return { s, ox: area.x + (area.w - width * s) / 2, oy: area.y + (area.h - height * s) / 2 }
}

export const Diagram: React.FC<BlockProps<DiagramProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const area = { x: stage.x, y: stage.y + 80, w: stage.w, h: stage.h - 80 - BASIS_H - 20 }
  const { s, ox, oy } = fitDiagram(p.width, p.height, area)
  const X = (v: number) => ox + v * s
  const Y = (v: number) => oy + v * s
  const labels: React.ReactNode[] = []
  const shapes = p.elements.map((e, i) => {
    const appear = firstCue(cues, 'show', e.id) ?? 10 + i * 8
    if (frame < appear) return null
    const k = progress(frame, appear, 20)
    const color = toneColor[e.tone]
    const common = { stroke: color, strokeWidth: 3, fill: 'none', strokeDasharray: e.dashed ? '10 8' : undefined }
    let anchor: { x: number; y: number } | null = null
    let shape: React.ReactNode = null
    switch (e.type) {
      case 'circle':
        shape = <circle cx={X(e.cx as number)} cy={Y(e.cy as number)} r={(e.r as number) * s * k} {...common} />
        anchor = { x: X(e.cx as number) + (e.r as number) * s + 12, y: Y(e.cy as number) - 14 }
        break
      case 'line':
      case 'arrow': {
        const x1 = X(e.x1 as number)
        const y1 = Y(e.y1 as number)
        const x2 = x1 + (X(e.x2 as number) - x1) * k
        const y2 = y1 + (Y(e.y2 as number) - y1) * k
        const ang = Math.atan2(y2 - y1, x2 - x1)
        shape = (
          <g>
            <line x1={x1} y1={y1} x2={x2} y2={y2} {...common} />
            {e.type === 'arrow' && k > 0.9 ? (
              <path d={`M${x2} ${y2} L${x2 - 18 * Math.cos(ang - 0.4)} ${y2 - 18 * Math.sin(ang - 0.4)} M${x2} ${y2} L${x2 - 18 * Math.cos(ang + 0.4)} ${y2 - 18 * Math.sin(ang + 0.4)}`} {...common} />
            ) : null}
          </g>
        )
        anchor = { x: (x1 + X(e.x2 as number)) / 2 + 12, y: (y1 + Y(e.y2 as number)) / 2 - 34 }
        break
      }
      case 'curve': {
        const pts = (e.points as [number, number][]).map(([x, y]) => `${X(x)},${Y(y)}`)
        shape = <polyline points={pts.slice(0, Math.max(2, Math.ceil(pts.length * k))).join(' ')} {...common} />
        const [lx, ly] = (e.points as [number, number][])[(e.points as [number, number][]).length - 1]
        anchor = { x: X(lx) + 12, y: Y(ly) - 16 }
        break
      }
      case 'orbit': {
        const cx = X(e.cx as number)
        const cy = Y(e.cy as number)
        const rx = (e.rx as number) * s
        const ry = (e.ry as number) * s
        const phase = (2 * Math.PI * (frame - appear)) / ((e.period as number) * fps)
        shape = (
          <g>
            <ellipse cx={cx} cy={cy} rx={rx} ry={ry} {...common} strokeOpacity={0.5 * k} />
            <circle cx={cx + rx * Math.cos(phase)} cy={cy + ry * Math.sin(phase)} r={10} fill={color} />
          </g>
        )
        anchor = { x: cx + rx + 12, y: cy - 16 }
        break
      }
      case 'label':
        anchor = { x: X(e.x as number), y: Y(e.y as number) }
        break
    }
    const text = e.type === 'label' ? e.text : e.label
    if (text && anchor) {
      labels.push(
        <LayoutBox key={e.id} id={`${sceneId}:el:${e.id}`} kind="text" style={{ position: 'absolute', left: anchor.x, top: anchor.y, whiteSpace: 'nowrap', ...hud(26, color), ...bootIn(frame, appear + 8, 10) }}>
          {text}
        </LayoutBox>,
      )
    }
    return <React.Fragment key={e.id}>{shape}</React.Fragment>
  })
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        {shapes}
      </svg>
      {labels}
      {p.basis ? (
        <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
          {`Schematic. Basis: ${p.basis}`}
        </LayoutBox>
      ) : null}
    </AbsoluteFill>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/blocks-infographics.test.ts`
Expected: `Tests  17 passed (17)`

- [ ] **Step 5: Commit**

```bash
git add video/src/blocks/ScaleDrawing.tsx video/src/blocks/UnitGrid.tsx video/src/blocks/BarChart.tsx video/src/blocks/ScaleZoom.tsx video/src/blocks/Timeline.tsx video/src/blocks/Diagram.tsx video/test/blocks-infographics.test.ts
git commit -m "Add the infographic blocks: to-scale drawing, unit grid, linear bar chart, scale zoom, timeline and diagram" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 17: The block table and the cue rules

**Files:**
- Create: `video/src/blocks/index.ts`
- Test: `video/test/blocks.test.ts`

`BLOCKS` maps each registry name to its component, its semantic check, the local cue verbs it takes with their valid targets, and the images `calculateMetadata` must measure. Its cue table is the single definition of which local verbs each block takes and which ids it shows; plan C's script check mirrors it (its `LOCAL_CUES` must cover exactly the blocks of `registry.json`). `checkBlocks` runs all of it over a parsed timeline (contract D3): a local verb must name a target the block shows, `introduce` needs a ClaimBoard listing the claim, a `meter` cue needs a Meter in the episode, a ShareCard may only be the last scene (owner rule for platform moments: never an advert, the link only on the end card and in the description; in a full episode and a slice alike), and every string the video draws must be drawable by the brand fonts (`DRAWABLE` of `theme/glyphs.ts`: the code points the loaded latin and latin-ext files map, Task 2), because the browser would silently draw any other character in a system font; that holds for a character inside a face's declared unicode-range that the file lacks, too (`Ḫ` of 'Ḫattuša', the non-breaking hyphen U+2011, `‰`). That includes the character's upper case: `heading()` and `hud()` draw upper case, so a teaser 'Set ƒ/8?' is refused for `ƒ` (drawn as `Ƒ`, which no loaded file maps). A teaser 'Smaller than 1 µm?' is refused for `µ` as written; `micrometre` is the drawable spelling. Only drawn strings are checked (owner decision 32, D1): `drawnStrings` walks the block's `drawn` paths from `schemas.ts`, `captureStrings` the drawn strings of every capture prop (its credits and `place`/`pin` labels), and the captions, credits, chapter titles and thumbnail teasers are checked as before. A `page` event's `title` (the source page's own `<title>`) is a record that nothing draws, so it is not checked. So an original quote shown only inside a captured page (SourceViewer), the page's non-latin title and a non-latin URL path pass, while a claim label or a credit the fonts cannot draw is refused.

- [ ] **Step 1: Write the failing test**

**`video/test/blocks.test.ts`** (complete file):

```ts
import { describe, expect, it } from 'vitest'

import { BLOCKS, checkBlocks, imagesToMeasure } from '../src/blocks'
import { REGISTRY_BLOCKS } from '../src/blocks/schemas'
import type { Capture } from '../src/blocks/types'
import { DEMO_TIMELINE } from '../src/fixtures/demo'
import { type Timeline, parseTimeline } from '../src/timeline'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = Record<string, any>

const clip: Capture = {
  id: 'pf1',
  kind: 'platform',
  src: 'captures/pf1.mp4',
  fps: 60,
  duration_s: 2.5,
  width: 2880,
  height: 1620,
  events: [],
  credits: ['© Mapbox © OpenStreetMap © Maxar'],
}

/** The demo timeline with its last scene, b12, replaced by `block`/`props` (180 frames = 3 s). */
function withScene(block: string, props: Json, cues: Json[] = []): Timeline {
  const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
  t.scenes[11] = { id: 'b12', from: 2040, durationInFrames: 180, block, props, cues }
  return parseTimeline(t)
}

/**
 * A source-page capture of the real Greek Wikipedia page: its URL path and its own
 * <title> are Greek; SourceViewer and the credit draw only the ASCII hostname.
 */
const page: Capture = {
  id: 'src1',
  kind: 'source',
  src: 'captures/src1.png',
  fps: null,
  duration_s: null,
  width: 2560,
  height: 3000,
  events: [
    { t: 0, name: 'gpu', label: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU)' },
    { t: 0, name: 'page', url: 'https://el.wikipedia.org/wiki/Κνωσός', title: 'Κνωσός - Βικιπαίδεια' },
    { t: 0, name: 'highlight', box: [200, 1500, 1800, 120], target: 'quote' },
  ],
  credits: ['Source page: el.wikipedia.org'],
}
/** Evidence whose verbatim quote is the Greek original: it sits in the page image, SourceViewer never draws it. */
const greekQuote: Json = {
  ...JSON.parse(JSON.stringify(DEMO_TIMELINE.scenes[1].props.evidence)),
  source: { url: 'https://el.wikipedia.org/wiki/Κνωσός', title: 'Knossos', tier: 2, license: '', quote: 'ἐν δὲ Κνωσός, μεγάλη πόλις', locator: 'lead' },
}

describe('the block library', () => {
  it('implements exactly the blocks of registry.json', () => {
    expect(Object.keys(BLOCKS).sort()).toEqual(Object.keys(REGISTRY_BLOCKS).sort())
  })
  it('measures the PhotoPlate images before the first frame', () => {
    const image = { id: 'm1', src: 'media/a.jpg', license: 'CC0', attribution: 'x', source_url: 'https://x.org', depicts: 'y', markers: [] }
    expect(imagesToMeasure(withScene('PhotoPlate', { image }))).toEqual(['media/a.jpg'])
  })
})

describe('checkBlocks', () => {
  it('passes the demo timeline', () => {
    expect(() => checkBlocks(parseTimeline(DEMO_TIMELINE))).not.toThrow()
  })
  it('refuses a local cue at a target the block does not show', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[4].cues[0].target = 'q9'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b05 \(ScaleDrawing\): show q9: not a target of this block \(q1, o2, o3\)/)
  })
  it('refuses a verb the block does not take', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[2].cues.push({ frame: 400, do: 'hide', target: 'x' })
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b03 \(Meter\): the block does not take hide cues/)
  })
  it('refuses an introduce cue for a claim no ClaimBoard lists', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[1].cues.push({ frame: 190, do: 'introduce', target: 'c9' })
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/introduce c9: no ClaimBoard of the episode lists this claim/)
  })
  it('refuses a meter cue in an episode without a Meter', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[2] = {
      id: 'b03',
      from: 360,
      durationInFrames: 180,
      block: 'ListCard',
      props: { title: 'x', items: [{ id: 'i9', text: 'y' }] },
      cues: [{ frame: 400, do: 'meter', target: 'meter', value: [70, 30] }],
    }
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/a meter cue needs a Meter scene/)
  })
  it('runs the block checks: meter start, clip length, map credits, marker boxes, diagram geometry', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[2].props.start = [60, 30]
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/meter start \[60,30\] must sum to 100/)
    expect(() => checkBlocks(withScene('PlatformClip', { clip }))).toThrow(/capture pf1 is 2.5 s long; the scene needs 3.000 s from 0 s/)
    const take = { ...clip, id: 'm1', kind: 'globe', width: 1920, height: 1080, duration_s: 5 }
    expect(() => checkBlocks(withScene('GlobeShot', { clip: take }))).toThrow(/carries map credits: a Mapbox take belongs in MapboxFlyover/)
    const image = { id: 'm1', src: 'media/a.jpg', license: 'CC0', attribution: 'x', source_url: 'https://x.org', depicts: 'y', markers: [{ id: 'mk1', box: [0.9, 0.5, 0.2, 0.1], label: '1 PERSON' }] }
    expect(() => checkBlocks(withScene('PhotoPlate', { image }))).toThrow(/marker mk1 box \[0.9,0.5,0.2,0.1\] is not a box inside the image/)
    const d: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    delete d.scenes[8].props.elements[1].r
    expect(() => checkBlocks(parseTimeline(d))).toThrow(/element d2 \(circle\) needs "r"/)
  })
  it('refuses text the brand fonts cannot draw, naming the scene, the path and the character', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[4].props.objects[1].label = 'Vinča figure'
    expect(() => checkBlocks(parseTimeline(t))).not.toThrow()
    t.scenes[4].props.objects[1].label = 'Κνωσός'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b05 \(ScaleDrawing\): props\.objects\[1\]\.label: "Κ" \(U\+039A\) has no glyph in the brand fonts/)
    // inside the declared latin-ext range, but the loaded JetBrains Mono file has no Ḫ
    t.scenes[4].props.objects[1].label = 'Ḫattuša'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b05 \(ScaleDrawing\): props\.objects\[1\]\.label: "Ḫ" \(U\+1E2A\) has no glyph in the brand fonts/)
    t.scenes[4].props.objects[1].label = 'Person'
    t.credits = [{ sceneId: 'b01', text: 'Photo → Commons' }]
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/timeline: credits\[0\]\.text \(scene b01\): "→" \(U\+2192\)/)
    t.credits = []
    t.thumbnails[0].text = 'Who → it?'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/timeline: thumbnails\[0\]\.text: "→" \(U\+2192\)/)
  })
  it('refuses a character whose upper case the brand fonts cannot draw (heading and hud draw upper case)', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.thumbnails[0].text = 'Set ƒ/8?'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(
      /timeline: thumbnails\[0\]\.text: "ƒ" \(U\+0192\) draws as "Ƒ" \(U\+0191\) in upper case, which has no glyph in the brand fonts/,
    )
  })
  it('refuses a ShareCard before the last scene: the link appears only on the end card', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[9] = { ...t.scenes[11], id: 'b10', from: 1620 }
    // the only error, so the last scene's ShareCard (b12) passes
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/:\n {2}scene b10 \(ShareCard\): ShareCard is the end card; only the last scene may use it$/)
  })
  it('checks only the strings the video draws: a page title, an original quote in a page image and a URL path pass (owner decision 32)', () => {
    expect(() => checkBlocks(withScene('SourceViewer', { page, evidence: greekQuote }))).not.toThrow()
  })
  it('refuses a drawn string outside the brand fonts: a claim label, a capture credit', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[0].props.claims[0].label = 'Κνωσός'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b01 \(ClaimBoard\): props\.claims\[0\]\.label: "Κ" \(U\+039A\)/)
    const greekCredit = { ...page, credits: ['Source page: Βικιπαίδεια'] }
    expect(() => checkBlocks(withScene('SourceViewer', { page: greekCredit, evidence: greekQuote }))).toThrow(
      /scene b12 \(SourceViewer\): props\.page\.credits\[0\]: "Β" \(U\+0392\)/,
    )
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/blocks.test.ts`
Expected: FAIL with `Cannot find module '../src/blocks'`.

- [ ] **Step 3: Implement**

**`video/src/blocks/index.ts`** (complete file):

```ts
/**
 * The scene block library. Every key here has an entry in schemas.ts
 * REGISTRY_BLOCKS (test/registry.test.ts keeps them equal). A block brings its
 * component, the semantic checks a schema cannot express, the local cue verbs
 * it interprets with their valid targets, and the images calculateMetadata must
 * measure for it. checkBlocks() runs the checks and the cue rules of a parsed
 * timeline: local verbs (show, hide, highlight, stamp) must name a target the
 * block shows; introduce needs a ClaimBoard listing the claim; a meter cue needs
 * a Meter in the episode; status cues may target any claim (EvidenceCard and
 * ClaimBoard show them). The cue table below is the single definition of the
 * local cue rules: plan C's script check mirrors it before voice and capture.
 * A ShareCard, the end card and the one place the link appears in the picture,
 * may only be the last scene (owner rule). Every string the video draws must be
 * drawable by the brand fonts, in upper case too (theme/glyphs.ts; owner
 * decision 32: only drawn strings are checked): the block's `drawn` prop paths
 * (schemas.ts), the drawn strings of its capture props (captureStrings), the
 * captions, credits, chapter titles and the thumbnail teasers.
 */
import type React from 'react'

import { glyphReason, unsupportedChar } from '../theme/glyphs'
import type { LocalVerb, Timeline } from '../timeline'
import { BarChart, type BarChartProps, checkBarChart } from './BarChart'
import { ClaimBoard, type ClaimBoardProps } from './ClaimBoard'
import { Diagram, type DiagramProps, checkDiagram } from './Diagram'
import { EvidenceCard, type EvidenceCardProps } from './EvidenceCard'
import { GlobeShot, type GlobeShotProps, checkGlobeShot, globePins } from './GlobeShot'
import { ListCard, type ListCardProps } from './ListCard'
import { MapboxFlyover, checkMapboxFlyover } from './MapboxFlyover'
import { MapboxTopdown, type MapboxTopdownProps, checkMapboxTopdown, pinsOf } from './MapboxTopdown'
import { Meter, checkMeter } from './Meter'
import { PhotoPlate, type PhotoPlateProps, checkPhotoPlate } from './PhotoPlate'
import { PlatformClip, checkPlatformClip } from './PlatformClip'
import { QuoteCard, type QuoteCardProps, checkQuoteCard } from './QuoteCard'
import { ScaleDrawing, type ScaleDrawingProps, checkScaleDrawing } from './ScaleDrawing'
import { ShareCard } from './ShareCard'
import { ScaleZoom, type ScaleZoomProps, checkScaleZoom } from './ScaleZoom'
import { CAPTURE_PROPS, REGISTRY_BLOCKS } from './schemas'
import { SourceViewer, type SourceViewerProps, checkSourceViewer } from './SourceViewer'
import { Timeline as TimelineBlock, type TimelineProps, checkTimeline } from './Timeline'
import type { BlockProps, Capture, CheckContext } from './types'
import { UnitGrid, type UnitGridProps, checkUnitGrid } from './UnitGrid'

type Targets<P> = (props: P) => string[]

export type BlockDef = {
  component: React.FC<BlockProps<unknown>>
  check: (props: unknown, ctx: CheckContext) => string[]
  cues: Partial<Record<LocalVerb, Targets<unknown>>>
  images: (props: unknown) => string[]
}

/** Erase the props type: parseTimeline() has validated the props against the block's schema. */
function block<P>(
  component: React.FC<BlockProps<P>>,
  opts: { check?: (props: P, ctx: CheckContext) => string[]; cues?: Partial<Record<LocalVerb, Targets<P>>>; images?: (props: P) => string[] } = {},
): BlockDef {
  return {
    component: component as unknown as React.FC<BlockProps<unknown>>,
    check: (props, ctx) => (opts.check ? opts.check(props as P, ctx) : []),
    cues: (opts.cues ?? {}) as Partial<Record<LocalVerb, Targets<unknown>>>,
    images: (props) => (opts.images ? opts.images(props as P) : []),
  }
}

const ids = (items: readonly { id: string }[]) => items.map((i) => i.id)
const markers = (p: PhotoPlateProps) => ids(p.image.markers)
const pins = (p: MapboxTopdownProps) => pinsOf(p.map).map((pin) => pin.id)
const evidence = (p: { evidence: { id: string } }) => [p.evidence.id]

export const BLOCKS: Record<string, BlockDef> = {
  PhotoPlate: block(PhotoPlate, { check: checkPhotoPlate, cues: { show: markers, hide: markers, highlight: markers }, images: (p) => [p.image.src] }),
  MapboxTopdown: block(MapboxTopdown, { check: checkMapboxTopdown, cues: { show: pins, highlight: pins } }),
  PlatformClip: block(PlatformClip, { check: checkPlatformClip }),
  GlobeShot: block(GlobeShot, { check: checkGlobeShot, cues: { show: (p: GlobeShotProps) => globePins(p.clip).map((pin) => pin.id) } }),
  MapboxFlyover: block(MapboxFlyover, { check: checkMapboxFlyover }),
  SourceViewer: block(SourceViewer, { check: checkSourceViewer, cues: { highlight: (p: SourceViewerProps) => evidence(p) } }),
  EvidenceCard: block(EvidenceCard, { cues: { highlight: (p: EvidenceCardProps) => evidence(p), stamp: (p: EvidenceCardProps) => evidence(p) } }),
  QuoteCard: block(QuoteCard, { check: checkQuoteCard, cues: { highlight: (p: QuoteCardProps) => evidence(p) } }),
  ClaimBoard: block(ClaimBoard, { cues: { highlight: (p: ClaimBoardProps) => ids(p.claims) } }),
  Meter: block(Meter, { check: checkMeter }),
  ScaleDrawing: block(ScaleDrawing, { check: checkScaleDrawing, cues: { show: (p: ScaleDrawingProps) => ids(p.objects) } }),
  UnitGrid: block(UnitGrid, { check: checkUnitGrid, cues: { show: (p: UnitGridProps) => ids(p.groups) } }),
  BarChart: block(BarChart, { check: checkBarChart, cues: { show: (p: BarChartProps) => ids(p.bars) } }),
  Timeline: block(TimelineBlock, { check: checkTimeline, cues: { show: (p: TimelineProps) => ids(p.events) } }),
  Diagram: block(Diagram, { check: checkDiagram, cues: { show: (p: DiagramProps) => ids(p.elements) } }),
  ListCard: block(ListCard, { cues: { show: (p: ListCardProps) => ids(p.items) } }),
  ShareCard: block(ShareCard),
  ScaleZoom: block(ScaleZoom, { check: checkScaleZoom, cues: { show: (p: ScaleZoomProps) => [p.small.id, p.large.id] } }),
}

export function blockDef(name: string): BlockDef {
  const def = BLOCKS[name]
  if (!def) throw new Error(`block ${name} has no component`)
  return def
}

/**
 * The strings a `drawn` pattern reaches in `value`, with their paths below `at`
 * ("props.claims[0].label"). Keys are separated by '.', a key suffixed with
 * '[]' walks every element of that array; an absent optional prop yields nothing.
 */
export function drawnStrings(value: unknown, patterns: readonly string[], at: string): [string, string][] {
  const walk = (v: unknown, parts: readonly string[], path: string): [string, string][] => {
    if (parts.length === 0) return typeof v === 'string' ? [[path, v]] : []
    if (typeof v !== 'object' || v === null || Array.isArray(v)) return []
    const [part, ...rest] = parts
    const key = part.endsWith('[]') ? part.slice(0, -2) : part
    const next = (v as Record<string, unknown>)[key]
    if (!part.endsWith('[]')) return walk(next, rest, `${path}.${key}`)
    return Array.isArray(next) ? next.flatMap((item, i) => walk(item, rest, `${path}.${key}[${i}]`)) : []
  }
  return patterns.flatMap((pattern) => walk(value, pattern.split('.'), at))
}

/**
 * The strings a capture puts on screen: its credits and the label of a globe
 * `place` or top-down `pin` event. Event names, targets, URLs (SourceViewer and
 * the cards draw only the ASCII hostname), a source `page` event's title (the
 * page's own <title>, kept as a record; owner decision 32) and the `gpu` event's
 * renderer are never drawn.
 */
export function captureStrings(capture: Pick<Capture, 'events' | 'credits'>, at: string): [string, string][] {
  const out: [string, string][] = capture.credits.map((c, i): [string, string] => [`${at}.credits[${i}]`, c])
  capture.events.forEach((e, i) => {
    if ((e.name === 'place' || e.name === 'pin') && e.label !== undefined) out.push([`${at}.events[${i}].label`, e.label])
  })
  return out
}

/** Every drawn string of a scene's props: the block's `drawn` paths and its capture props' drawn strings. */
function sceneStrings(block: string, props: Record<string, unknown>): [string, string][] {
  const captures = CAPTURE_PROPS.filter((k) => k in props).flatMap((k) => captureStrings(props[k] as Capture, `props.${k}`))
  return [...drawnStrings(props, REGISTRY_BLOCKS[block].drawn, 'props'), ...captures]
}

/** The error for a character of `text` the brand fonts cannot draw, as written or in upper case, or null. */
function glyphProblem(where: string, at: string, text: string): string | null {
  const ch = unsupportedChar(text)
  return ch === null ? null : `${where}: ${at}: ${glyphReason(ch)}`
}

/** Throws with every semantic defect, every bad cue and every undrawable character of the timeline. */
export function checkBlocks(timeline: Timeline): void {
  const errors: string[] = []
  const boardClaims = new Set(
    timeline.scenes.filter((s) => s.block === 'ClaimBoard').flatMap((s) => ids((s.props as unknown as ClaimBoardProps).claims)),
  )
  const hasMeter = timeline.scenes.some((s) => s.block === 'Meter')
  const texts: [string, string][] = [
    ...timeline.captions.map((c, i): [string, string] => [`captions[${i}].text`, c.text]),
    ...timeline.credits.map((c, i): [string, string] => [`credits[${i}].text (scene ${c.sceneId})`, c.text]),
    ...timeline.chapters.map((c, i): [string, string] => [`chapters[${i}].title`, c.title]),
    ...timeline.thumbnails.map((c, i): [string, string] => [`thumbnails[${i}].text`, c.text]),
  ]
  for (const [at, text] of texts) {
    const problem = glyphProblem('timeline', at, text)
    if (problem) errors.push(problem)
  }
  const last = timeline.scenes[timeline.scenes.length - 1]
  for (const scene of timeline.scenes) {
    const def = blockDef(scene.block)
    const where = `scene ${scene.id} (${scene.block})`
    // owner rule: the link appears only on the end card (and in the description)
    if (scene.block === 'ShareCard' && scene !== last) errors.push(`${where}: ShareCard is the end card; only the last scene may use it`)
    for (const e of def.check(scene.props, { fps: timeline.fps, durationInFrames: scene.durationInFrames })) errors.push(`${where}: ${e}`)
    for (const [at, text] of sceneStrings(scene.block, scene.props)) {
      const problem = glyphProblem(where, at, text)
      if (problem) errors.push(problem)
    }
    for (const cue of scene.cues) {
      if (cue.do === 'introduce') {
        if (!boardClaims.has(cue.target)) errors.push(`${where}: introduce ${cue.target}: no ClaimBoard of the episode lists this claim`)
      } else if (cue.do === 'meter') {
        if (!hasMeter) errors.push(`${where}: a meter cue needs a Meter scene in the episode`)
      } else if (cue.do !== 'status') {
        const targets = def.cues[cue.do]
        if (!targets) errors.push(`${where}: the block does not take ${cue.do} cues`)
        else if (!targets(scene.props).includes(cue.target)) errors.push(`${where}: ${cue.do} ${cue.target}: not a target of this block (${targets(scene.props).join(', ') || 'none'})`)
      }
    }
  }
  if (errors.length) throw new Error(`timeline.json block checks failed:\n  ${errors.join('\n  ')}`)
}

/** Every image calculateMetadata measures before the first frame. */
export function imagesToMeasure(timeline: Timeline): string[] {
  return timeline.scenes.flatMap((s) => blockDef(s.block).images(s.props))
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/blocks.test.ts`
Expected: `Tests  13 passed (13)`

- [ ] **Step 5: Commit**

```bash
git add video/src/blocks/index.ts video/test/blocks.test.ts
git commit -m "Tie every registry block to its component, checks and cue targets" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 18: The Episode and Thumbnail compositions

**Files:**
- Create: `video/src/SceneView.tsx`, `video/src/Episode.tsx`, `video/src/Thumbnail.tsx`, `video/src/Root.tsx`, `video/src/index.ts`
- Test: `video/test/rules.test.ts`

Both compositions take the timeline as an input prop. `calculateMetadata` runs once per render in the browser: it parses and checks the timeline, measures every narration clip and image, sets duration, fps and size from the timeline, and puts the browser's WebGL renderer into the props as `gpu` (the scripts refuse anything but the NVIDIA). Episode mounts one `<Sequence>` per scene, the overlays, one `<Audio>` per narration clip and the looping music bed with its duck curve; in lint mode it mounts `LayoutGuard` instead of the audio. Thumbnail shows candidate K of the timeline's three thumbnail candidates (owner decisions 24-25): one episode frame without captions, ticker or chapter tag; with the scene's in-frame credit line (spec 4.8), with the candidate's teaser in the NERV heading type (Orbitron, upper case, 104 px, at most two lines) on its own dark glass in `TEASER_ZONE`, inside the title-safe area and clear of the bottom-right 25 % x 20 % of the frame, where YouTube lays its duration badge. The credit line is that of the scene that shows the frame (`creditsAt`: the `timeline.credits` texts of the scene with `from <= frame < from + durationInFrames`), merged as in the episode and drawn bottom left in `THUMBNAIL_CREDIT_ZONE` (the size of `ZONES.credit`, inside the title-safe area, clear of the teaser, the duration badge and the lower third; the episode's credit zone lies under the badge, so `EpisodeVisuals` keeps `credits={false}`); a scene without credits gets none. A thumbnail taken in a PhotoPlate, PlatformClip, MapboxTopdown or MapboxFlyover scene thus keeps its photo or Mapbox/Maxar attribution in the picture, which the Mapbox terms require and which the same JPEG needs as the paper page's poster. The teaser is the only box the Thumbnail measures in lint mode (`lint.ts` renders each candidate once; an overflowing teaser is an `overflow` violation); the scene under it is linted with the episode and covered on purpose, and the credit line is the scene's own (same text, same box size), which the episode lint measures; it sits where the episode's player controls would be, and a thumbnail has none. `test/rules.test.ts` enforces the Remotion rules over all of `src/` and pins the teaser zone, the credit zone and the credit selection.

- [ ] **Step 1: Write the failing test**

**`video/test/rules.test.ts`** (complete file):

```ts
import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { Episode, EpisodeVisuals } from '../src/Episode'
import { DEMO_TIMELINE } from '../src/fixtures/demo'
import { contains, overlapArea } from '../src/layout/geometry'
import { SAFE, ZONES } from '../src/layout/zones'
import { SceneView } from '../src/SceneView'
import { DURATION_BADGE, TEASER_ZONE, THUMBNAIL_CREDIT_ZONE, Thumbnail, creditsAt, teaserOf } from '../src/Thumbnail'

const SRC = fileURLToPath(new URL('../src', import.meta.url))

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) return sources(full)
    return /\.tsx?$/.test(name) ? [full] : []
  })
}

/** Remotion renders frames out of order in parallel tabs: every frame must be a pure function of its number. */
const RULES: [RegExp, string][] = [
  [/Math\.random/, 'randomness only through random(seed) from remotion'],
  [/Date\.now|new Date\(|performance\.now/, 'time comes from useCurrentFrame(), never the clock'],
  [/setTimeout|setInterval|requestAnimationFrame/, 'no timers inside a frame render'],
  [/\b(transition|animation|animationName)\s*:/, 'no CSS transitions or animations'],
  [/@keyframes/, 'no CSS keyframes'],
  [/<(OffthreadVideo|Html5Video|Html5Audio)\b/, '<Video> and <Audio> come from @remotion/media'],
  [/import\s*\{[^}]*\b(Audio|Video)\b[^}]*\}\s*from\s*'remotion'/, '<Video> and <Audio> come from @remotion/media'],
  [/<(video|audio|img)\b/, 'native media tags do not hold the frame until they loaded'],
  [/backgroundImage|background-image/, 'no CSS background images'],
]

describe('Remotion rules over every file in src/', () => {
  const files = sources(SRC)
  it('finds the renderer sources', () => {
    expect(files.length).toBeGreaterThan(40)
  })
  it.each(RULES)('%s', (pattern, rule) => {
    const offenders = files.filter((f) => pattern.test(readFileSync(f, 'utf-8'))).map((f) => path.relative(SRC, f))
    expect(offenders, rule).toEqual([])
  })
})

describe('compositions', () => {
  it('export the components Root registers', () => {
    for (const component of [Episode, EpisodeVisuals, SceneView, Thumbnail]) expect(typeof component).toBe('function')
  })
  it('register Episode and Thumbnail with their size and length from the timeline', () => {
    const root = readFileSync(path.join(SRC, 'Root.tsx'), 'utf-8')
    expect(root).toContain('id="Episode"')
    expect(root).toContain('id="Thumbnail"')
    expect(root.match(/calculateMetadata=\{/g)).toHaveLength(2)
    expect(root).toContain('gpu: webglRenderer()')
  })
})

describe('thumbnail teaser and credit line (owner decisions 24-25, spec 4.8)', () => {
  it('sit inside the title-safe area and clear of the duration badge YouTube lays over a thumbnail', () => {
    expect(contains(SAFE, TEASER_ZONE)).toBe(true)
    expect(overlapArea(TEASER_ZONE, DURATION_BADGE)).toBe(0)
    // the scene's credit line: bottom left, the size of the episode's credit zone, clear of teaser, badge and lower third
    expect(contains(SAFE, THUMBNAIL_CREDIT_ZONE)).toBe(true)
    for (const other of [TEASER_ZONE, DURATION_BADGE, ZONES.lowerThird]) expect(overlapArea(THUMBNAIL_CREDIT_ZONE, other)).toBe(0)
    expect([THUMBNAIL_CREDIT_ZONE.w, THUMBNAIL_CREDIT_ZONE.h]).toEqual([ZONES.credit.w, ZONES.credit.h])
  })
  it('draws the teaser of the chosen candidate and refuses one the timeline does not have', () => {
    expect(teaserOf(DEMO_TIMELINE, 2)).toBe('Eighty buses heavy?')
    expect(() => teaserOf(DEMO_TIMELINE, 4)).toThrow(/thumbnail candidate 4 does not exist \(1\.\.3\)/)
  })
  it('takes the credit line of the scene that shows the frame, and none from a scene without credits', () => {
    const scene = DEMO_TIMELINE.scenes[1]
    const credits = [
      { sceneId: scene.id, text: 'Photo: Jane Doe (CC BY-SA 4.0)' },
      { sceneId: scene.id, text: '© Mapbox © Maxar' },
    ]
    const timeline = { ...DEMO_TIMELINE, credits }
    expect(creditsAt(timeline, scene.from)).toEqual(['Photo: Jane Doe (CC BY-SA 4.0)', '© Mapbox © Maxar'])
    expect(creditsAt(timeline, scene.from + scene.durationInFrames - 1)).toEqual(['Photo: Jane Doe (CC BY-SA 4.0)', '© Mapbox © Maxar'])
    expect(creditsAt(timeline, scene.from - 1)).toEqual([])
    expect(creditsAt(timeline, scene.from + scene.durationInFrames)).toEqual([])
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/rules.test.ts`
Expected: FAIL with `Cannot find module '../src/Episode'`.

- [ ] **Step 3: Implement**

**`video/src/SceneView.tsx`** (complete file):

```tsx
/**
 * One scene inside its <Sequence>: the block with scene-relative cues and its
 * stage (shorter while hook captions run), plus the scene's in-frame credit
 * line when timeline.credits names the scene and credits are drawn.
 */
import React from 'react'
import { AbsoluteFill } from 'remotion'

import { blockDef } from './blocks'
import { CreditLine } from './blocks/CreditLine'
import { mergeCredits } from './captions'
import { stageFor } from './layout/zones'
import type { Scene } from './timeline'

export const SceneView: React.FC<{ scene: Scene; credits: readonly string[]; captioned: boolean }> = ({ scene, credits, captioned }) => {
  const Block = blockDef(scene.block).component
  const cues = scene.cues.map((c) => ({ ...c, frame: c.frame - scene.from }))
  return (
    <AbsoluteFill>
      <Block props={scene.props} cues={cues} durationInFrames={scene.durationInFrames} sceneId={scene.id} sceneFrom={scene.from} stage={stageFor(captioned)} />
      {credits.length > 0 ? <CreditLine id={`${scene.id}:credit`} text={mergeCredits(credits)} /> : null}
    </AbsoluteFill>
  )
}
```

**`video/src/Episode.tsx`** (complete file):

```tsx
/**
 * The Episode composition: one <Sequence> per scene, the global overlays
 * (chapter tag, evidence ticker, hook captions), the narration clips and the
 * ducked music bed. In lint mode (inputProps.lint, set by scripts/lint.ts)
 * LayoutGuard reports every layout violation of the frame, no audio is mounted
 * and clips are not decoded.
 */
import React, { useMemo } from 'react'
import { Audio } from '@remotion/media'
import { AbsoluteFill, Sequence, staticFile } from 'remotion'

import { type Span, musicVolume } from './audio'
import { ChapterTag } from './blocks/ChapterTag'
import { HookCaptions } from './blocks/HookCaptions'
import { Ticker } from './blocks/Ticker'
import { EpisodeContext, type ImageSizes } from './context'
import { LayoutProvider, Registry } from './layout/LayoutBox'
import { LayoutGuard } from './layout/LayoutGuard'
import { SceneView } from './SceneView'
import { buildState } from './state'
import { colors } from './theme/colors'
import { type Timeline, sceneHasCaptions } from './timeline'

export type EpisodeProps = {
  timeline: Timeline
  lint: boolean
  /** Filled by calculateMetadata from the narration files; [] in inputProps. */
  narrationSpans: Span[]
  /** Filled by calculateMetadata from the images; {} in inputProps. */
  imageSizes: ImageSizes
  /** Filled by calculateMetadata: the render browser's WebGL renderer (src/gpu.ts); '' in inputProps. */
  gpu: string
}

/**
 * All scenes and, with `overlays`, the chapter tag, ticker and hook captions.
 * `shift` moves every scene earlier by that many frames: the one-frame
 * Thumbnail composition passes the wanted episode frame, so its frame 0 shows
 * exactly that moment.
 */
export const EpisodeVisuals: React.FC<{ timeline: Timeline; overlays: boolean; credits: boolean; shift: number }> = ({ timeline, overlays, credits, shift }) => {
  const creditsByScene = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const c of timeline.credits) map.set(c.sceneId, [...(map.get(c.sceneId) ?? []), c.text])
    return map
  }, [timeline])
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      {timeline.scenes.map((scene) => (
        <Sequence key={scene.id} name={`${scene.id} ${scene.block}`} from={scene.from - shift} durationInFrames={scene.durationInFrames}>
          <SceneView scene={scene} credits={credits ? (creditsByScene.get(scene.id) ?? []) : []} captioned={overlays && sceneHasCaptions(timeline, scene)} />
        </Sequence>
      ))}
      {overlays ? (
        <>
          <ChapterTag chapters={timeline.chapters} />
          <Ticker steps={timeline.ticker.evidence} />
          <HookCaptions captions={timeline.captions} />
        </>
      ) : null}
    </AbsoluteFill>
  )
}

const EpisodeAudio: React.FC<{ timeline: Timeline; spans: readonly Span[] }> = ({ timeline, spans }) => {
  const music = timeline.audio.music
  return (
    <>
      {timeline.audio.narration.map((clip, i) => (
        <Sequence key={`${clip.src}-${i}`} name={`voice ${clip.src}`} from={clip.from} layout="none">
          <Audio src={staticFile(clip.src)} disallowFallbackToHtml5Audio />
        </Sequence>
      ))}
      {music ? (
        <Audio src={staticFile(music.src)} loop loopVolumeCurveBehavior="extend" volume={(f) => musicVolume(f, music, spans)} disallowFallbackToHtml5Audio />
      ) : null}
    </>
  )
}

export const Episode: React.FC<EpisodeProps> = ({ timeline, lint, narrationSpans, imageSizes }) => {
  const registry = useMemo(() => new Registry(lint), [lint])
  const data = useMemo(() => ({ state: buildState(timeline.scenes), imageSizes, lint }), [timeline, imageSizes, lint])
  return (
    <EpisodeContext.Provider value={data}>
      <LayoutProvider registry={registry}>
        <EpisodeVisuals timeline={timeline} overlays credits shift={0} />
        {/* Lint renders sparse frames (everyNthFrame) and checks layout only: no audio. */}
        {lint ? <LayoutGuard /> : <EpisodeAudio timeline={timeline} spans={narrationSpans} />}
      </LayoutProvider>
    </EpisodeContext.Provider>
  )
}
```

**`video/src/Thumbnail.tsx`** (complete file):

```tsx
/**
 * The Thumbnail composition (owner decisions 24-25): episode frame `frame`
 * without captions, ticker or chapter tag; with the scene's in-frame credit
 * line (spec 4.8), with the teaser of thumbnail candidate `candidate`
 * (timeline.thumbnails: 2-4 words, a question or riddle that never gives the
 * answer; plan C picks the frames and the words) in the NERV heading type on
 * its own dark glass. The composition is one frame long and shifts every scene
 * by `frame`, so its only frame shows that moment (scene motion included). The
 * teaser sits in TEASER_ZONE: inside the title-safe area and clear of the
 * bottom-right corner, where YouTube lays its duration badge over a thumbnail.
 * The credit line of the scene that shows the frame (photo licence, source
 * page, Mapbox/Maxar: the Mapbox terms want the attribution in the picture, and
 * the JPEG is also the paper page's poster) sits bottom left in
 * THUMBNAIL_CREDIT_ZONE, because the episode's credit zone lies under the
 * badge; a scene without credits gets none. In lint mode (scripts/lint.ts)
 * only the teaser is measured: the scene under it is linted with the episode,
 * and the teaser covers it on purpose; the credit line is the scene's own (same
 * text, same box size), which the episode lint measures, and it sits where the
 * episode's player controls would be, which a thumbnail does not have.
 * scripts/still.ts renders it at scale 2 (3840x2160 master) and as a 1280x720
 * JPEG under 2 MB.
 */
import React, { useMemo } from 'react'

import { CreditLine } from './blocks/CreditLine'
import { mergeCredits } from './captions'
import type { ImageSizes } from './context'
import { EpisodeContext } from './context'
import { EpisodeVisuals } from './Episode'
import type { Rect } from './layout/geometry'
import { LayoutBox, LayoutProvider, Registry } from './layout/LayoutBox'
import { LayoutGuard } from './layout/LayoutGuard'
import { buildState } from './state'
import { colors } from './theme/colors'
import { heading } from './theme/type'
import type { Timeline } from './timeline'

export type ThumbnailProps = { timeline: Timeline; candidate: number; frame: number; lint: boolean; imageSizes: ImageSizes; gpu: string }

/** Where the teaser goes: the top of the frame, inside the title-safe area. */
export const TEASER_ZONE: Rect = { x: 96, y: 72, w: 1440, h: 380 }
/** YouTube lays its duration badge over the bottom-right corner of a thumbnail (25 % x 20 % of the frame). */
export const DURATION_BADGE: Rect = { x: 1440, y: 864, w: 480, h: 216 }
/**
 * Where the credit line of the frame's scene goes: bottom left inside the title-safe area,
 * the size of ZONES.credit, clear of TEASER_ZONE, DURATION_BADGE and ZONES.lowerThird.
 */
export const THUMBNAIL_CREDIT_ZONE: Rect = { x: 96, y: 984, w: 800, h: 32 }

/** The teaser of candidate `candidate` (1-based, like still.ts --candidate). */
export function teaserOf(timeline: Pick<Timeline, 'thumbnails'>, candidate: number): string {
  const c = Number.isInteger(candidate) ? timeline.thumbnails[candidate - 1] : undefined
  if (!c) throw new Error(`thumbnail candidate ${candidate} does not exist (1..${timeline.thumbnails.length})`)
  return c.text
}

/** The timeline.credits texts of the scene that shows episode frame `frame`, in timeline order ([] for a scene without credits). */
export function creditsAt(timeline: Pick<Timeline, 'scenes' | 'credits'>, frame: number): string[] {
  const scene = timeline.scenes.find((s) => s.from <= frame && frame < s.from + s.durationInFrames)
  if (!scene) throw new Error(`no scene shows episode frame ${frame}`)
  return timeline.credits.filter((c) => c.sceneId === scene.id).map((c) => c.text)
}

export const Thumbnail: React.FC<ThumbnailProps> = ({ timeline, candidate, frame, lint, imageSizes }) => {
  const scenes = useMemo(() => new Registry(false), [])
  const teaser = useMemo(() => new Registry(lint), [lint])
  const data = useMemo(() => ({ state: buildState(timeline.scenes), imageSizes, lint }), [timeline, imageSizes, lint])
  const credits = creditsAt(timeline, frame)
  const z = TEASER_ZONE
  return (
    <EpisodeContext.Provider value={data}>
      <LayoutProvider registry={scenes}>
        <EpisodeVisuals timeline={timeline} overlays={false} credits={false} shift={frame} />
        {credits.length > 0 ? <CreditLine id={`thumbnail${candidate}:credit`} text={mergeCredits(credits)} zone={THUMBNAIL_CREDIT_ZONE} /> : null}
      </LayoutProvider>
      <LayoutProvider registry={teaser}>
        <div style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, background: colors.bgPanel }} />
        <div style={{ position: 'absolute', left: z.x, top: z.y, width: 10, height: z.h, background: colors.green }} />
        <LayoutBox
          id={`thumbnail${candidate}:teaser`}
          kind="text"
          style={{ position: 'absolute', left: z.x + 44, top: z.y + 24, width: z.w - 72, height: z.h - 48, overflow: 'hidden', display: 'flex', alignItems: 'center', ...heading(104) }}
        >
          {teaserOf(timeline, candidate)}
        </LayoutBox>
        {lint ? <LayoutGuard /> : null}
      </LayoutProvider>
    </EpisodeContext.Provider>
  )
}
```

**`video/src/Root.tsx`** (complete file):

```tsx
/**
 * Compositions. Both take the timeline as an input prop; calculateMetadata
 * validates it (parseTimeline + checkBlocks), measures the narration clips and
 * the images in the browser, and sets duration, fps and size from the
 * timeline, so nothing about an episode is hard-coded here. The default props
 * are the graphics-only demo timeline for `npm run studio`.
 */
import React from 'react'
import { type CalculateMetadataFunction, Composition } from 'remotion'

import { narrationSpans } from './audio'
import { checkBlocks, imagesToMeasure } from './blocks'
import { Episode, type EpisodeProps } from './Episode'
import { DEMO_TIMELINE } from './fixtures/demo'
import { webglRenderer } from './gpu'
import { audioSeconds, measureImages } from './media'
import { loadBrandFonts } from './theme/fonts'
import { Thumbnail, type ThumbnailProps, teaserOf } from './Thumbnail'
import { parseTimeline } from './timeline'

loadBrandFonts()

const episodeMetadata: CalculateMetadataFunction<EpisodeProps> = async ({ props }) => {
  const timeline = parseTimeline(props.timeline)
  checkBlocks(timeline)
  const seconds = await Promise.all(timeline.audio.narration.map((n) => audioSeconds(n.src)))
  const imageSizes = await measureImages(imagesToMeasure(timeline))
  return {
    durationInFrames: timeline.durationInFrames,
    fps: timeline.fps,
    width: timeline.width,
    height: timeline.height,
    props: { ...props, timeline, imageSizes, narrationSpans: narrationSpans(timeline.audio.narration, seconds, timeline.fps), gpu: webglRenderer() },
  }
}

const thumbnailMetadata: CalculateMetadataFunction<ThumbnailProps> = async ({ props }) => {
  const timeline = parseTimeline(props.timeline)
  checkBlocks(timeline)
  teaserOf(timeline, props.candidate)
  if (!Number.isInteger(props.frame) || props.frame < 0 || props.frame >= timeline.durationInFrames) {
    throw new Error(`Thumbnail frame ${props.frame} is outside the episode (0..${timeline.durationInFrames - 1})`)
  }
  const imageSizes = await measureImages(imagesToMeasure(timeline))
  return { durationInFrames: 1, fps: timeline.fps, width: timeline.width, height: timeline.height, props: { ...props, timeline, imageSizes, gpu: webglRenderer() } }
}

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Episode"
      component={Episode}
      defaultProps={{ timeline: DEMO_TIMELINE, lint: false, narrationSpans: [], imageSizes: {}, gpu: '' }}
      calculateMetadata={episodeMetadata}
      durationInFrames={1}
      fps={60}
      width={1920}
      height={1080}
    />
    <Composition
      id="Thumbnail"
      component={Thumbnail}
      defaultProps={{ timeline: DEMO_TIMELINE, candidate: 1, frame: DEMO_TIMELINE.thumbnails[0].frame, lint: false, imageSizes: {}, gpu: '' }}
      calculateMetadata={thumbnailMetadata}
      durationInFrames={1}
      fps={60}
      width={1920}
      height={1080}
    />
  </>
)
```

**`video/src/index.ts`** (complete file):

```ts
import { registerRoot } from 'remotion'

import { RemotionRoot } from './Root'

registerRoot(RemotionRoot)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/rules.test.ts && npx tsc --noEmit`
Expected: `Tests  15 passed (15)`, then no tsc output.

- [ ] **Step 5: Commit**

```bash
git add video/src/SceneView.tsx video/src/Episode.tsx video/src/Thumbnail.tsx video/src/Root.tsx video/src/index.ts video/test/rules.test.ts
git commit -m "Compose the Episode and Thumbnail from timeline.json with duration, size and GPU proof from calculateMetadata" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 19: Script helpers: flags, chunks, violation lines and the GPU rules

**Files:**
- Create: `video/scripts/args.ts`
- Test: `video/test/args.test.ts`

Pure helpers of the three scripts. `nvidiaProblem` judges the renderer string every script reads from its browser; `nvencOverride` is the `ffmpegOverride` of every render: the video encode must be `h264_nvenc`, it gets `-gpu 0 -bf 0`, and any other encoder (a software encode) throws (spec 4.11). Measured 2026-09-26 on the workstation: Remotion's default `gl` puts the headless shell on SwiftShader and `angle-egl` on the Basic Render Driver; `gl: 'angle'` draws on the NVIDIA; `hardwareAcceleration: 'required'` makes Remotion choose `h264_nvenc` and fail when its ffmpeg lacks it.

- [ ] **Step 1: Write the failing test**

**`video/test/args.test.ts`** (complete file):

```ts
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { VIOLATION_TYPE, violationLine } from '../src/layout/LayoutGuard'
import { VIOLATION_PREFIX, bundleDir, chunkRanges, concatList, nvencOverride, nvidiaProblem, parseFlags, parseViolation, progressPrinter } from '../scripts/args'

const spec = {
  timeline: { required: true, kind: 'path' as const },
  every: { required: false, kind: 'int' as const },
  scale: { required: false, kind: 'number' as const },
}

describe('parseFlags', () => {
  it('parses paths absolute and numbers typed', () => {
    expect(parseFlags(['--timeline', 't.json', '--every', '6', '--scale', '0.5'], spec)).toEqual({
      timeline: path.resolve('t.json'),
      every: 6,
      scale: 0.5,
    })
  })
  it.each([
    [['--every', '6'], /missing required flag --timeline/],
    [['--timeline'], /--timeline needs a value/],
    [['--timeline', 't.json', '--bogus', '1'], /unknown flag --bogus/],
    [['--timeline', 't.json', '--every', '1.5'], /--every must be a non-negative integer/],
    [['--timeline', 't.json', '--scale', '0'], /--scale must be a positive number/],
    [['t.json'], /unexpected argument "t\.json"/],
  ])('rejects %j', (argv, message) => {
    expect(() => parseFlags(argv, spec)).toThrow(message)
  })
})

describe('chunkRanges', () => {
  it('covers every frame exactly once', () => {
    expect(chunkRanges(600, 300)).toEqual([
      [0, 299],
      [300, 599],
    ])
    expect(chunkRanges(601, 300)).toEqual([
      [0, 299],
      [300, 599],
      [600, 600],
    ])
    expect(chunkRanges(100, 3600)).toEqual([[0, 99]])
  })
})

describe('parseViolation', () => {
  it('reads LayoutGuard lines and ignores every other log line', () => {
    expect(VIOLATION_PREFIX).toBe(`{"type":"${VIOLATION_TYPE}"`)
    const line = violationLine(12, { a: 'captions', b: 'b01:lt', reason: 'overlap' })
    expect(parseViolation(line)).toEqual({ type: 'layout-violation', frame: 12, a: 'captions', b: 'b01:lt', reason: 'overlap' })
    expect(parseViolation('Warning: something else')).toBeNull()
  })
})

describe('the GPU rule (spec 4.11)', () => {
  it('accepts only a render browser on the NVIDIA', () => {
    expect(nvidiaProblem('ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)')).toBeNull()
    for (const other of [
      'ANGLE (AMD, AMD Radeon(TM) Graphics (0x00001681) Direct3D11 vs_5_0 ps_5_0, D3D11)',
      'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)',
      'ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)',
      '',
    ]) {
      expect(nvidiaProblem(other)).toMatch(/not the NVIDIA GPU/)
    }
  })
  it('pins h264_nvenc to GPU 0 without B-frames, passes stream copies and refuses software encoders', () => {
    const pre = ['-r', '60', '-i', '-', '-c:v', 'h264_nvenc', '-pix_fmt', 'yuv420p', '-b:v', '16M', 'out.mp4']
    expect(nvencOverride({ type: 'pre-stitcher', args: pre })).toEqual(['-r', '60', '-i', '-', '-c:v', 'h264_nvenc', '-gpu', '0', '-bf', '0', '-pix_fmt', 'yuv420p', '-b:v', '16M', 'out.mp4'])
    const copy = ['-i', 'pre.mp4', '-c:v', 'copy', 'out.mp4']
    expect(nvencOverride({ type: 'stitcher', args: copy })).toEqual(copy)
    expect(nvencOverride({ type: 'stitcher', args: ['-i', 'a.wav', 'b.aac'] })).toEqual(['-i', 'a.wav', 'b.aac'])
    expect(() => nvencOverride({ type: 'pre-stitcher', args: ['-c:v', 'libx264', 'out.mp4'] })).toThrow(/only h264_nvenc is allowed/)
  })
})

describe('concatList', () => {
  it('lists the chunks for the ffmpeg concat demuxer, forward slashes and quotes escaped', () => {
    const windows = ['C:', 'ep', 'render', 'raw.mp4.parts', 'video-000.mp4'].join('\\')
    expect(concatList([windows, "C:/it's/video-001.mp4"])).toBe(["file 'C:/ep/render/raw.mp4.parts/video-000.mp4'", "file 'C:/it'\\''s/video-001.mp4'", ''].join('\n'))
  })
})

describe('progressPrinter', () => {
  it('prints each step once, however often progress is reported', () => {
    const lines: string[] = []
    const report = progressPrinter('render', 25, (l) => lines.push(l))
    for (const f of [0, 0.1, 0.1, 0.3, 0.8, 1]) report(f)
    expect(lines).toEqual(['render 0%', 'render 25%', 'render 50%', 'render 75%', 'render 100%'])
  })
})

describe('bundleDir', () => {
  it('bundles next to the public dir (the episode drive), never into the system temp dir', () => {
    expect(bundleDir(path.join('ep', 'render', 'public'))).toBe(path.resolve('ep', 'render', 'bundle'))
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/args.test.ts`
Expected: FAIL with `Cannot find module '../scripts/args'`.

- [ ] **Step 3: Implement**

**`video/scripts/args.ts`** (complete file):

```ts
/**
 * Pure helpers of the node scripts (no Remotion imports; test/args.test.ts):
 * strict flag parsing, render chunk ranges, the lint violation lines
 * LayoutGuard writes to the browser console, progress reporting in steps, and
 * the two GPU rules of spec section 4.11: the render browser must draw on the
 * NVIDIA, and every video encode must be h264_nvenc on GPU 0.
 */
import path from 'node:path'

import { VIOLATION_TYPE } from '../src/layout/LayoutGuard'

export type FlagSpec = Record<string, { required: boolean; kind: 'path' | 'int' | 'number' | 'string' }>
export type Flags = Record<string, string | number>

/** Parse `--name value` pairs; unknown flags, missing values and missing required flags throw. */
export function parseFlags(argv: readonly string[], spec: FlagSpec): Flags {
  const out: Flags = {}
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (!arg.startsWith('--')) throw new Error(`unexpected argument "${arg}"`)
    const name = arg.slice(2)
    const def = spec[name]
    if (!def) throw new Error(`unknown flag --${name} (known: ${Object.keys(spec).map((k) => `--${k}`).join(', ')})`)
    const value = argv[++i]
    if (value === undefined || value.startsWith('--')) throw new Error(`--${name} needs a value`)
    if (def.kind === 'int') {
      const n = Number(value)
      if (!Number.isInteger(n) || n < 0) throw new Error(`--${name} must be a non-negative integer, got "${value}"`)
      out[name] = n
    } else if (def.kind === 'number') {
      const n = Number(value)
      if (!Number.isFinite(n) || n <= 0) throw new Error(`--${name} must be a positive number, got "${value}"`)
      out[name] = n
    } else {
      out[name] = def.kind === 'path' ? path.resolve(value) : value
    }
  }
  for (const [name, def] of Object.entries(spec)) {
    if (def.required && !(name in out)) throw new Error(`missing required flag --${name}`)
  }
  return out
}

/** [start, end] inclusive frame ranges of at most `size` frames covering the episode. */
export function chunkRanges(durationInFrames: number, size: number): [number, number][] {
  if (size < 1) throw new Error('chunk size must be >= 1')
  const out: [number, number][] = []
  for (let s = 0; s < durationInFrames; s += size) out.push([s, Math.min(durationInFrames, s + size) - 1])
  return out
}

export const VIOLATION_PREFIX = `{"type":"${VIOLATION_TYPE}"`

export type LintViolation = { type: typeof VIOLATION_TYPE; frame: number; a: string; b: string | null; reason: string }

/** The violation carried by one browser console line, or null for any other log line. */
export function parseViolation(text: string): LintViolation | null {
  if (!text.startsWith(VIOLATION_PREFIX)) return null
  return JSON.parse(text) as LintViolation
}

/** A progress callback that prints "<label> NN%" once per `step` percent, one line each. */
export function progressPrinter(label: string, step = 10, write: (line: string) => void = (l) => console.log(l)): (fraction: number) => void {
  let next = 0
  return (fraction) => {
    const pct = Math.floor(fraction * 100)
    while (pct >= next && next <= 100) {
      write(`${label} ${next}%`)
      next += step
    }
  }
}

/** Renderer strings that are not the NVIDIA: the integrated AMD, software rasterisers, the fallback adapter. */
const NOT_NVIDIA = /AMD|Radeon|SwiftShader|Basic Render|llvmpipe|Intel/i

/** Why a WebGL renderer string (src/gpu.ts) is not the NVIDIA, or null when it is. */
export function nvidiaProblem(renderer: string): string | null {
  if (!/NVIDIA/.test(renderer) || NOT_NVIDIA.test(renderer)) {
    return `the render browser draws on "${renderer || 'no renderer'}", not the NVIDIA GPU (spec 4.11); run \`python -m pipeline.studio doctor\``
  }
  return null
}

export type FfmpegStep = { type: 'pre-stitcher' | 'stitcher'; args: string[] }

/**
 * Remotion's ffmpegOverride for every render: each video encode must be
 * h264_nvenc; it runs on GPU 0 (the NVIDIA, the only CUDA device) and without
 * B-frames, so render.ts can join its chunks by stream copy. Stream copies
 * pass; any other encoder is a software encode and fails the render.
 */
export function nvencOverride({ args }: FfmpegStep): string[] {
  const i = args.indexOf('-c:v')
  if (i < 0) return args
  const encoder = args[i + 1]
  if (encoder === 'copy') return args
  if (encoder !== 'h264_nvenc') throw new Error(`Remotion chose the video encoder "${encoder}"; only h264_nvenc is allowed (spec 4.11)`)
  return [...args.slice(0, i + 2), '-gpu', '0', '-bf', '0', ...args.slice(i + 2)]
}

/** The ffconcat list of the rendered chunks (forward slashes, quotes escaped). */
export function concatList(files: readonly string[]): string {
  return files.map((f) => `file '${f.replace(/\\/g, '/').replace(/'/g, "'\\''")}'`).join('\n') + '\n'
}

/**
 * Where a script bundles: `bundle/` next to the per-render public dir
 * (<episode>/render/bundle). Remotion's bundle() copies the whole public dir
 * into its output (on Windows always as a copy), so the default output in the
 * system temp dir would put a second copy of every capture on C: per script.
 */
export function bundleDir(publicDir: string): string {
  return path.join(path.dirname(path.resolve(publicDir)), 'bundle')
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/args.test.ts`
Expected: `Tests  14 passed (14)`

- [ ] **Step 5: Commit**

```bash
git add video/scripts/args.ts video/test/args.test.ts
git commit -m "Add the render scripts' helpers: strict flags, chunk ranges, lint lines and the NVIDIA and NVENC rules" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 20: lint.ts, render.ts and still.ts

**Files:**
- Create: `video/scripts/cli.ts`, `video/scripts/lint.ts`, `video/scripts/render.ts`, `video/scripts/still.ts`
- Test: `video/test/scripts.test.ts`

Contract D4 (plan C's C9). `cli.ts` loads and checks the timeline, checks that the public dir holds every referenced file and the brand fonts before Chrome starts, bundles with that public dir into `bundle/` next to it (`withBundle`: Remotion's `bundle()` copies the whole public dir, byte for byte on Windows, into its output, by default a fresh `%TEMP%` directory it never deletes; the per-render public dir holds voice, music and every HEVC capture, so three scripts per render would leave three copies of it on C:. `withBundle` removes its bundle when the work ends, on success and on failure, so at most one copy exists, on the episode's own drive, while one script runs), and opens every browser through `onNvidia`: `openBrowser('chrome', {chromiumOptions: {gl: 'angle'}})`, resolve the composition in it, refuse unless its `gpu` prop names the NVIDIA, print `gpu: <renderer>`. `render.ts` renders the episode in chunks of at most 3600 frames, each in a fresh browser (the angle backend leaks memory on long renders): `h264` with `hardwareAcceleration: 'required'`, `nvencOverride`, 16 Mbit/s and `colorSpace: 'bt709'`, the chunk's audio to a separate PCM WAV (`separateAudioTo`, `enforceAudioTrack` so a silent chunk still has its samples). At 48 kHz and 60 fps a frame is exactly 800 samples, so the WAV parts join sample-exactly and the video parts frame-exactly with the ffmpeg concat demuxer; the joined audio is encoded to AAC 320k once here (plan C's `render.py` re-encodes it once more at 320k after its loudness gain) and the frame count is checked against the timeline. (A single audio-only pass over the whole episode was tried first: Remotion still renders every frame for it, clips included, and it ran longer than the video itself.) `lint.ts` lints the episode frames and then each thumbnail candidate's teaser (the Thumbnail composition in lint mode, one frame per candidate, each in its own browser proved on the NVIDIA). `still.ts --candidate K [--frame N]` renders one of the three candidates (owner decision 24) as `thumbnail_<K>_3840.png` and `thumbnail_<K>_1280.jpg`, at the candidate's frame or at `--frame N`; plan C calls it once per candidate.

- [ ] **Step 1: Write the failing test**

**`video/test/scripts.test.ts`** (complete file):

```ts
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const VIDEO_ROOT = fileURLToPath(new URL('..', import.meta.url))
/** A cold `node --import tsx` compiles the scripts first (about 10 s on the workstation). */
const SLOW = 60_000

/** Run a node script the way pipeline/studio/render.py does (tsx), without a browser. */
function run(script: string, args: string[]) {
  return spawnSync(process.execPath, ['--import', 'tsx', `scripts/${script}`, ...args], { cwd: VIDEO_ROOT, encoding: 'utf-8', timeout: 60_000 })
}

describe('the node scripts fail with exit code 1 and a precise message (plan C contract C9)', () => {
  it.each([
    ['lint.ts', []],
    ['render.ts', ['--out', 'out.mp4']],
    ['still.ts', ['--out-dir', 'out', '--candidate', '1']],
  ])('%s refuses a timeline that does not exist', (script, extra) => {
    const result = run(script, ['--timeline', 'no-such-timeline.json', '--public-dir', '.', ...extra])
    expect(result.status).toBe(1)
    expect(result.stderr).toMatch(/timeline not found: .*no-such-timeline\.json/)
  }, SLOW)
  it('refuses unknown and missing flags', () => {
    const unknown = run('render.ts', ['--timeline', 't.json', '--public-dir', '.', '--out', 'o.mp4', '--crf', '18'])
    expect(unknown.status).toBe(1)
    expect(unknown.stderr).toMatch(/unknown flag --crf/)
    const missing = run('still.ts', ['--timeline', 't.json', '--public-dir', '.'])
    expect(missing.status).toBe(1)
    expect(missing.stderr).toMatch(/missing required flag --out-dir/)
  }, SLOW)
  it('still.ts renders one of the three thumbnail candidates (owner decision 24)', () => {
    const noCandidate = run('still.ts', ['--timeline', 't.json', '--public-dir', '.', '--out-dir', 'o'])
    expect(noCandidate.status).toBe(1)
    expect(noCandidate.stderr).toMatch(/missing required flag --candidate/)
    const fourth = run('still.ts', ['--timeline', 't.json', '--public-dir', '.', '--out-dir', 'o', '--candidate', '4'])
    expect(fourth.status).toBe(1)
    expect(fourth.stderr).toMatch(/--candidate must be 1\.\.3, got 4/)
  }, SLOW)
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/scripts.test.ts`
Expected: FAIL — 5 failed: the scripts do not exist, so node exits with `ERR_MODULE_NOT_FOUND` instead of the messages.

- [ ] **Step 3: Implement**

**`video/scripts/cli.ts`** (complete file):

```ts
/**
 * Shared plumbing of render.ts, lint.ts and still.ts: loading and checking
 * timeline.json, checking the per-render public dir, bundling with it (into
 * bundle/ next to it, removed afterwards), the render browser on the NVIDIA
 * (proved, spec 4.11) and ffmpeg/ffprobe (the binaries pipeline/video/media.py
 * uses: $FFMPEG_BIN / $FFPROBE_BIN, else PATH). Every failure throws; run()
 * turns it into exit code 1 with the message on stderr.
 */
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { bundle } from '@remotion/bundler'
import { type HeadlessBrowser, openBrowser, selectComposition } from '@remotion/renderer'

import { checkBlocks } from '../src/blocks'
import { FONT_FILES } from '../src/theme/fonts'
import { type Timeline, collectSrcs, parseTimeline } from '../src/timeline'
import { bundleDir, nvidiaProblem, progressPrinter } from './args'

export const VIDEO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
export const FFMPEG = process.env.FFMPEG_BIN ?? 'ffmpeg'
export const FFPROBE = process.env.FFPROBE_BIN ?? 'ffprobe'

export function loadTimeline(file: string): Timeline {
  if (!existsSync(file)) throw new Error(`timeline not found: ${file}`)
  const timeline = parseTimeline(JSON.parse(readFileSync(file, 'utf-8')))
  checkBlocks(timeline)
  return timeline
}

/** Every file the timeline references, and the brand fonts, must exist in the public dir before Chrome starts. */
export function assertAssets(timeline: Timeline, publicDir: string): void {
  if (!existsSync(publicDir)) throw new Error(`public dir not found: ${publicDir}`)
  const wanted = new Set<string>([...FONT_FILES, ...collectSrcs([timeline.audio, timeline.scenes])])
  const missing = [...wanted].filter((rel) => !existsSync(path.join(publicDir, rel)))
  if (missing.length) throw new Error(`public dir ${publicDir} lacks: ${missing.join(', ')}`)
}

/**
 * Bundle with the public dir into bundleDir(publicDir), run `work` on the bundle and
 * delete the bundle when `work` ends, successfully or not. bundle() copies the whole
 * public dir into its output; its default output, a fresh directory in the system temp
 * dir, is never deleted, so every script run would leave a copy of every capture on C:.
 */
export async function withBundle<T>(publicDir: string, work: (serveUrl: string) => Promise<T>): Promise<T> {
  const outDir = bundleDir(publicDir)
  rmSync(outDir, { recursive: true, force: true })
  try {
    const report = progressPrinter('bundle', 25)
    const serveUrl = await bundle({ entryPoint: path.join(VIDEO_ROOT, 'src', 'index.ts'), publicDir, outDir, onProgress: (p) => report(p / 100) })
    return await work(serveUrl)
  } finally {
    rmSync(outDir, { recursive: true, force: true })
  }
}

type Composition = Awaited<ReturnType<typeof selectComposition>>

/**
 * Open a render browser with the ANGLE/D3D11 backend (Remotion's default picks
 * SwiftShader), resolve the composition in it and prove from its WebGL renderer
 * (the `gpu` prop calculateMetadata sets) that it draws on the NVIDIA. The
 * browser is closed when `work` ends, successfully or not.
 */
export async function onNvidia<T>(
  serveUrl: string,
  id: 'Episode' | 'Thumbnail',
  inputProps: Record<string, unknown>,
  work: (browser: HeadlessBrowser, composition: Composition) => Promise<T>,
): Promise<T> {
  const browser = await openBrowser('chrome', { chromiumOptions: { gl: 'angle' } })
  try {
    const composition = await selectComposition({ serveUrl, id, inputProps, puppeteerInstance: browser })
    const problem = nvidiaProblem(String(composition.props.gpu ?? ''))
    if (problem) throw new Error(problem)
    console.log(`gpu: ${composition.props.gpu}`)
    return await work(browser, composition)
  } finally {
    await browser.close({ silent: true })
  }
}

/** Run ffmpeg (quiet, overwrite); a non-zero exit throws with ffmpeg's stderr. */
export function ffmpeg(args: readonly string[]): void {
  execFileSync(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-y', ...args], { stdio: ['ignore', 'ignore', 'pipe'] })
}

/** Frames of the first video stream, counted by decoding (the audit's count). */
export function countFrames(file: string): number {
  const out = execFileSync(FFPROBE, ['-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', file], {
    encoding: 'utf-8',
  })
  return Number(out.trim())
}

export function run(main: () => Promise<void>): void {
  main().then(
    () => process.exit(0),
    (err: unknown) => {
      console.error(err instanceof Error ? (err.stack ?? err.message) : String(err))
      process.exit(1)
    },
  )
}
```

**`video/scripts/lint.ts`** (complete file):

```ts
/**
 * Layout lint pass (plan C contract C9), cwd video/:
 *   node --import tsx scripts/lint.ts --timeline <timeline.json> --public-dir <dir>
 *        [--every 6] [--scale 0.5] [--report <lint.json>] [--concurrency N]
 * Renders every Nth frame at reduced scale with inputProps.lint = true (no
 * audio, clips not decoded); LayoutGuard logs each violation as a
 * console.error JSON line, collected here through onBrowserLog. Then the
 * teaser of each thumbnail candidate (the Thumbnail composition in lint mode,
 * one frame each; its violations carry the candidate's episode frame). Every
 * browser is proved to draw on the NVIDIA first (cli.ts onNvidia, spec 4.11).
 * Every violation is printed to stderr as that JSON line; the exit code is 1
 * when there is at least one. --report also writes {frames, every, scale,
 * violations}; frames counts the episode frames and the thumbnails checked.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

import { renderFrames } from '@remotion/renderer'

import { type LintViolation, parseFlags, parseViolation } from './args'
import { assertAssets, loadTimeline, onNvidia, run, withBundle } from './cli'

export const DEFAULT_EVERY = 6
export const DEFAULT_SCALE = 0.5

run(async () => {
  const flags = parseFlags(process.argv.slice(2), {
    timeline: { required: true, kind: 'path' },
    'public-dir': { required: true, kind: 'path' },
    every: { required: false, kind: 'int' },
    scale: { required: false, kind: 'number' },
    report: { required: false, kind: 'path' },
    concurrency: { required: false, kind: 'int' },
  })
  const timeline = loadTimeline(flags.timeline as string)
  const publicDir = flags['public-dir'] as string
  assertAssets(timeline, publicDir)
  const every = (flags.every as number | undefined) ?? DEFAULT_EVERY
  const scale = (flags.scale as number | undefined) ?? DEFAULT_SCALE
  if (every < 1) throw new Error('--every must be >= 1')
  const inputProps = { timeline, lint: true, narrationSpans: [], imageSizes: {}, gpu: '' }
  const violations: LintViolation[] = []
  let frames = 0
  // The frames themselves are thrown away: only LayoutGuard's console output matters.
  const discard = { imageFormat: 'jpeg', jpegQuality: 50, muted: true, outputDir: null, onFrameBuffer: () => undefined, timeoutInMilliseconds: 120_000 } as const
  await withBundle(publicDir, async (serveUrl) => {
    await onNvidia(serveUrl, 'Episode', inputProps, (browser, composition) =>
      renderFrames({
        ...discard,
        composition,
        serveUrl,
        inputProps,
        puppeteerInstance: browser,
        everyNthFrame: every,
        scale,
        concurrency: (flags.concurrency as number | undefined) ?? null,
        onStart: ({ frameCount }) => console.log(`lint: ${frameCount} frames (every ${every}, scale ${scale})`),
        onFrameUpdate: (rendered) => {
          frames = rendered
        },
        onBrowserLog: (log) => {
          const v = parseViolation(log.text)
          if (v) violations.push(v)
        },
      }),
    )
    for (const [i, thumb] of timeline.thumbnails.entries()) {
      const thumbProps = { timeline, candidate: i + 1, frame: thumb.frame, lint: true, imageSizes: {}, gpu: '' }
      await onNvidia(serveUrl, 'Thumbnail', thumbProps, (browser, composition) =>
        renderFrames({
          ...discard,
          composition,
          serveUrl,
          inputProps: thumbProps,
          puppeteerInstance: browser,
          scale,
          concurrency: 1,
          onStart: () => console.log(`lint: thumbnail ${i + 1} (frame ${thumb.frame})`),
          onFrameUpdate: () => undefined,
          onBrowserLog: (log) => {
            const v = parseViolation(log.text)
            if (v) violations.push({ ...v, frame: thumb.frame })
          },
        }),
      )
      frames += 1
    }
  })
  if (flags.report) {
    const report = flags.report as string
    mkdirSync(path.dirname(report), { recursive: true })
    writeFileSync(report, JSON.stringify({ frames, every, scale, violations }, null, 2))
  }
  for (const v of violations) console.error(JSON.stringify(v))
  if (violations.length) throw new Error(`${violations.length} layout violation(s) in ${frames} checked frames`)
  console.log(`lint clean: ${frames} frames checked`)
})
```

**`video/scripts/render.ts`** (complete file):

```ts
/**
 * Render an episode (plan C contract C9), cwd video/:
 *   node --import tsx scripts/render.ts --timeline <timeline.json> --public-dir <dir> --out <file.mp4>
 *        [--chunk-frames 3600] [--concurrency N]
 * H.264 (NVENC) + AAC 320k, 1920x1080 at the timeline's 60 fps, BT.709.
 *
 * GPU rule (spec 4.11): every chunk renders in a fresh browser whose WebGL
 * renderer is proved to be the NVIDIA (cli.ts onNvidia), and encodes with
 * hardwareAcceleration 'required' (no software fallback) plus nvencOverride,
 * which pins h264_nvenc to GPU 0 and fails on any other encoder.
 *
 * Chunks: the episode renders in frameRange chunks of at most --chunk-frames
 * frames, each in its own browser (the angle GL backend leaks memory on long
 * renders). Each chunk writes its video without B-frames and its audio (the
 * narration clips and the ducked music bed) as a separate 16-bit PCM WAV: at
 * 48 kHz and 60 fps a frame is exactly 800 samples, so the WAV parts join
 * sample-exactly and the video parts frame-exactly, both by the ffmpeg concat
 * demuxer. The joined audio is encoded to AAC 320k once here;
 * pipeline/studio/render.py re-encodes it once at 320k after the loudness
 * gain. The frame count is checked against the timeline. Exit code 1 on any
 * failure.
 */
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import path from 'node:path'

import { renderMedia } from '@remotion/renderer'

import { chunkRanges, concatList, nvencOverride, parseFlags, progressPrinter } from './args'
import { assertAssets, countFrames, ffmpeg, loadTimeline, onNvidia, run, withBundle } from './cli'

export const VIDEO_BITRATE = '16M'
export const AUDIO_BITRATE = '320k'
export const DEFAULT_CHUNK_FRAMES = 3600

run(async () => {
  const flags = parseFlags(process.argv.slice(2), {
    timeline: { required: true, kind: 'path' },
    'public-dir': { required: true, kind: 'path' },
    out: { required: true, kind: 'path' },
    'chunk-frames': { required: false, kind: 'int' },
    concurrency: { required: false, kind: 'int' },
  })
  const timeline = loadTimeline(flags.timeline as string)
  const publicDir = flags['public-dir'] as string
  assertAssets(timeline, publicDir)
  const out = flags.out as string
  const chunkFrames = (flags['chunk-frames'] as number | undefined) ?? DEFAULT_CHUNK_FRAMES
  const concurrency = (flags.concurrency as number | undefined) ?? null
  const inputProps = { timeline, lint: false, narrationSpans: [], imageSizes: {}, gpu: '' }
  const parts = `${out}.parts`
  rmSync(parts, { recursive: true, force: true })
  mkdirSync(parts, { recursive: true })
  const ranges = chunkRanges(timeline.durationInFrames, chunkFrames)
  const videoFiles: string[] = []
  const audioFiles: string[] = []
  await withBundle(publicDir, async (serveUrl) => {
    for (const [i, range] of ranges.entries()) {
      const name = path.join(parts, `part-${String(i).padStart(3, '0')}`)
      const report = progressPrinter(`part ${i + 1}/${ranges.length}`, 25)
      await onNvidia(serveUrl, 'Episode', inputProps, (browser, composition) =>
        renderMedia({
          composition,
          serveUrl,
          inputProps,
          puppeteerInstance: browser,
          codec: 'h264',
          frameRange: range,
          outputLocation: `${name}.mp4`,
          audioCodec: 'pcm-16',
          separateAudioTo: `${name}.wav`,
          enforceAudioTrack: true,
          hardwareAcceleration: 'required',
          videoBitrate: VIDEO_BITRATE,
          ffmpegOverride: nvencOverride,
          colorSpace: 'bt709',
          concurrency,
          timeoutInMilliseconds: 120_000,
          onProgress: ({ progress }) => report(progress),
        }),
      )
      videoFiles.push(`${name}.mp4`)
      audioFiles.push(`${name}.wav`)
    }
  })
  const videoList = path.join(parts, 'video.ffconcat')
  const audioList = path.join(parts, 'audio.ffconcat')
  writeFileSync(videoList, concatList(videoFiles))
  writeFileSync(audioList, concatList(audioFiles))
  mkdirSync(path.dirname(out), { recursive: true })
  ffmpeg([
    ...['-f', 'concat', '-safe', '0', '-i', videoList, '-f', 'concat', '-safe', '0', '-i', audioList],
    ...['-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', AUDIO_BITRATE, '-ar', '48000'],
    ...['-movflags', '+faststart', out],
  ])
  const frames = countFrames(out)
  if (frames !== timeline.durationInFrames) throw new Error(`${out} has ${frames} frames; the timeline has ${timeline.durationInFrames}`)
  rmSync(parts, { recursive: true, force: true })
  console.log(out)
})
```

**`video/scripts/still.ts`** (complete file):

```ts
/**
 * Thumbnail candidates (plan C contract C9; owner decisions 24-25), cwd video/:
 *   node --import tsx scripts/still.ts --timeline <timeline.json> --public-dir <dir> --out-dir <dir>
 *        --candidate K [--frame N]
 * Renders candidate K (1-3) of timeline.thumbnails: the Thumbnail composition
 * (the episode frame without captions, ticker or chapter tag; with the scene's
 * in-frame credit line (spec 4.8), bottom left, and the candidate's teaser) at
 * the candidate's frame, or at --frame N (plan C's
 * `episode thumbnail SLUG --candidate K --frame N`), as thumbnail_<K>_3840.png
 * (scale 2, 3840x2160 master) and thumbnail_<K>_1280.jpg (1280x720; quality
 * steps down from 92 until the file is under 2 MB, YouTube's limit), in a
 * browser proved to draw on the NVIDIA (cli.ts onNvidia, spec 4.11). lint.ts
 * checks each teaser's layout; the teaser does not depend on the frame.
 */
import { mkdirSync, statSync } from 'node:fs'
import path from 'node:path'

import { renderStill } from '@remotion/renderer'

import { THUMBNAIL_CANDIDATES } from '../src/timeline'
import { parseFlags } from './args'
import { assertAssets, loadTimeline, onNvidia, run, withBundle } from './cli'

export const masterName = (candidate: number) => `thumbnail_${candidate}_3840.png`
export const jpegName = (candidate: number) => `thumbnail_${candidate}_1280.jpg`
export const MAX_JPEG_BYTES = 2 * 1024 * 1024
export const JPEG_QUALITIES = [92, 88, 84, 80, 76, 72, 68] as const

run(async () => {
  const flags = parseFlags(process.argv.slice(2), {
    timeline: { required: true, kind: 'path' },
    'public-dir': { required: true, kind: 'path' },
    'out-dir': { required: true, kind: 'path' },
    candidate: { required: true, kind: 'int' },
    frame: { required: false, kind: 'int' },
  })
  const candidate = flags.candidate as number
  if (candidate < 1 || candidate > THUMBNAIL_CANDIDATES) throw new Error(`--candidate must be 1..${THUMBNAIL_CANDIDATES}, got ${candidate}`)
  const timeline = loadTimeline(flags.timeline as string)
  const publicDir = flags['public-dir'] as string
  assertAssets(timeline, publicDir)
  const outDir = flags['out-dir'] as string
  const frame = (flags.frame as number | undefined) ?? timeline.thumbnails[candidate - 1].frame
  const inputProps = { timeline, candidate, frame, lint: false, imageSizes: {}, gpu: '' }
  mkdirSync(outDir, { recursive: true })
  const master = path.join(outDir, masterName(candidate))
  const jpeg = path.join(outDir, jpegName(candidate))
  const fitted = await withBundle(publicDir, (serveUrl) =>
    onNvidia(serveUrl, 'Thumbnail', inputProps, async (browser, composition) => {
      await renderStill({ composition, serveUrl, inputProps, output: master, imageFormat: 'png', scale: 3840 / composition.width, puppeteerInstance: browser })
      for (const quality of JPEG_QUALITIES) {
        await renderStill({ composition, serveUrl, inputProps, output: jpeg, imageFormat: 'jpeg', jpegQuality: quality, scale: 1280 / composition.width, puppeteerInstance: browser })
        if (statSync(jpeg).size < MAX_JPEG_BYTES) return true
      }
      return false
    }),
  )
  if (!fitted) throw new Error(`${jpeg} stays above 2 MB even at quality ${JPEG_QUALITIES[JPEG_QUALITIES.length - 1]}`)
  console.log(`candidate ${candidate}, frame ${frame}\n${master}\n${jpeg}`)
})
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/scripts.test.ts && npx tsc --noEmit`
Expected: `Tests  5 passed (5)`, then no tsc output.

- [ ] **Step 5: Commit**

```bash
git add video/scripts/cli.ts video/scripts/lint.ts video/scripts/render.ts video/scripts/still.ts video/test/scripts.test.ts
git commit -m "Add the layout lint, the chunked NVENC render and the thumbnail scripts, each proving its browser runs on the NVIDIA" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 21: The smoke-render fixture

**Files:**
- Create: `video/test/fixtures/smoke-timeline.json`
- Test: `video/test/smoke.test.ts`

A 10-second, 600-frame timeline with every footage block (PhotoPlate, PlatformClip, GlobeShot, MapboxTopdown, SourceViewer, EvidenceCard), narration, a ducked music bed, hook captions, ticker, chapters, credits and three thumbnail candidates. Task 22 renders it locally, together with the graphics-only demo timeline of Task 8 (every other block); the test keeps it valid and pins the assets Task 22 generates.

- [ ] **Step 1: Write the failing test**

**`video/test/smoke.test.ts`** (complete file):

```ts
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { checkBlocks, imagesToMeasure } from '../src/blocks'
import { collectSrcs, parseTimeline } from '../src/timeline'

const FIXTURE = fileURLToPath(new URL('./fixtures/smoke-timeline.json', import.meta.url))

describe('the smoke-render fixture (plan D local smoke task)', () => {
  const timeline = parseTimeline(JSON.parse(readFileSync(FIXTURE, 'utf-8')))
  it('is a valid 10-second timeline with every footage block', () => {
    expect(() => checkBlocks(timeline)).not.toThrow()
    expect(timeline.durationInFrames).toBe(600)
    expect(timeline.scenes.map((s) => s.block)).toEqual(['PhotoPlate', 'PlatformClip', 'GlobeShot', 'MapboxTopdown', 'SourceViewer', 'EvidenceCard'])
  })
  it('references exactly the assets the smoke task generates', () => {
    expect([...new Set(collectSrcs([timeline.audio, timeline.scenes]))].sort()).toEqual([
      'captures/globe.mp4',
      'captures/page.png',
      'captures/platform.mp4',
      'captures/topdown.jpg',
      'media/plate.jpg',
      'music/bed.wav',
      'voice/b01.mp3',
      'voice/b02.mp3',
    ])
    expect(imagesToMeasure(timeline)).toEqual(['media/plate.jpg'])
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd video && npx vitest run test/smoke.test.ts`
Expected: FAIL with `ENOENT: no such file or directory, open '...\video\test\fixtures\smoke-timeline.json'`.

- [ ] **Step 3: Implement**

**`video/test/fixtures/smoke-timeline.json`** (complete file):

```json
{
  "version": 1,
  "fps": 60,
  "width": 1920,
  "height": 1080,
  "durationInFrames": 600,
  "audio": {
    "narration": [
      {
        "src": "voice/b01.mp3",
        "from": 12
      },
      {
        "src": "voice/b02.mp3",
        "from": 300
      }
    ],
    "music": {
      "src": "music/bed.wav",
      "gainDb": -8,
      "duck": {
        "underNarrationDb": -12,
        "attackFrames": 6,
        "releaseFrames": 24
      }
    }
  },
  "scenes": [
    {
      "id": "s1",
      "from": 0,
      "durationInFrames": 150,
      "block": "PhotoPlate",
      "props": {
        "image": {
          "id": "m1",
          "src": "media/plate.jpg",
          "license": "CC BY-SA 4.0",
          "attribution": "Smoke Test",
          "source_url": "https://commons.wikimedia.org/wiki/File:Smoke.jpg",
          "depicts": "a test pattern standing in for the stone",
          "markers": [
            {
              "id": "mk1",
              "box": [
                0.42,
                0.38,
                0.14,
                0.2
              ],
              "label": "1 PERSON"
            }
          ]
        },
        "kenBurns": "in",
        "label": {
          "title": "Test plate",
          "subtitle": "smoke render"
        }
      },
      "cues": [
        {
          "frame": 30,
          "do": "show",
          "target": "mk1"
        },
        {
          "frame": 122,
          "do": "highlight",
          "target": "mk1"
        }
      ]
    },
    {
      "id": "s2",
      "from": 150,
      "durationInFrames": 120,
      "block": "PlatformClip",
      "props": {
        "clip": {
          "id": "pf1",
          "kind": "platform",
          "src": "captures/platform.mp4",
          "fps": 60,
          "duration_s": 4.0,
          "width": 2880,
          "height": 1620,
          "events": [
            {
              "t": 0.4,
              "name": "pause_rotation"
            },
            {
              "t": 1.0,
              "name": "search",
              "x": 540.0,
              "y": 350.0
            }
          ],
          "credits": [
            "© Mapbox © OpenStreetMap © Maxar"
          ]
        },
        "start_s": 0.5,
        "follow": 1.5
      },
      "cues": []
    },
    {
      "id": "s3",
      "from": 270,
      "durationInFrames": 120,
      "block": "GlobeShot",
      "props": {
        "clip": {
          "id": "g1",
          "kind": "globe",
          "src": "captures/globe.mp4",
          "fps": 60,
          "duration_s": 3.0,
          "width": 1920,
          "height": 1080,
          "events": [
            {
              "t": 0.0,
              "name": "rotate"
            },
            {
              "t": 0.5,
              "name": "zoom"
            },
            {
              "t": 1.0,
              "name": "arrive",
              "x": 960.0,
              "y": 540.0
            },
            {
              "t": 1.0,
              "name": "place",
              "x": 900.0,
              "y": 560.0,
              "target": "p1",
              "label": "Baalbek",
              "track": [[900.0, 560.0], [900.5, 559.8], [901.0, 559.7], [901.5, 559.5], [902.0, 559.3], [902.5, 559.2], [903.0, 559.0], [903.5, 558.8], [904.0, 558.7], [904.5, 558.5], [905.0, 558.3], [905.5, 558.2], [906.1, 558.0], [906.6, 557.8], [907.1, 557.6], [907.6, 557.5], [908.1, 557.3], [908.6, 557.1], [909.1, 557.0], [909.6, 556.8], [910.1, 556.6], [910.6, 556.5], [911.1, 556.3], [911.6, 556.1], [912.1, 556.0], [912.6, 555.8], [913.1, 555.6], [913.6, 555.5], [914.1, 555.3], [914.6, 555.1], [915.1, 555.0], [915.6, 554.8], [916.1, 554.6], [916.6, 554.5], [917.1, 554.3], [917.6, 554.1], [918.2, 553.9], [918.7, 553.8], [919.2, 553.6], [919.7, 553.4], [920.2, 553.3], [920.7, 553.1], [921.2, 552.9], [921.7, 552.8], [922.2, 552.6], [922.7, 552.4], [923.2, 552.3], [923.7, 552.1], [924.2, 551.9], [924.7, 551.8], [925.2, 551.6], [925.7, 551.4], [926.2, 551.3], [926.7, 551.1], [927.2, 550.9], [927.7, 550.8], [928.2, 550.6], [928.7, 550.4], [929.2, 550.3], [929.7, 550.1], [930.3, 549.9], [930.8, 549.7], [931.3, 549.6], [931.8, 549.4], [932.3, 549.2], [932.8, 549.1], [933.3, 548.9], [933.8, 548.7], [934.3, 548.6], [934.8, 548.4], [935.3, 548.2], [935.8, 548.1], [936.3, 547.9], [936.8, 547.7], [937.3, 547.6], [937.8, 547.4], [938.3, 547.2], [938.8, 547.1], [939.3, 546.9], [939.8, 546.7], [940.3, 546.6], [940.8, 546.4], [941.3, 546.2], [941.8, 546.1], [942.4, 545.9], [942.9, 545.7], [943.4, 545.5], [943.9, 545.4], [944.4, 545.2], [944.9, 545.0], [945.4, 544.9], [945.9, 544.7], [946.4, 544.5], [946.9, 544.4], [947.4, 544.2], [947.9, 544.0], [948.4, 543.9], [948.9, 543.7], [949.4, 543.5], [949.9, 543.4], [950.4, 543.2], [950.9, 543.0], [951.4, 542.9], [951.9, 542.7], [952.4, 542.5], [952.9, 542.4], [953.4, 542.2], [953.9, 542.0], [954.5, 541.8], [955.0, 541.7], [955.5, 541.5], [956.0, 541.3], [956.5, 541.2], [957.0, 541.0], [957.5, 540.8], [958.0, 540.7], [958.5, 540.5], [959.0, 540.3], [959.5, 540.2], [960.0, 540.0]]
            }
          ],
          "credits": []
        },
        "label": {
          "title": "Baalbek",
          "subtitle": "Beqaa Valley, Lebanon"
        }
      },
      "cues": []
    },
    {
      "id": "s4",
      "from": 390,
      "durationInFrames": 90,
      "block": "MapboxTopdown",
      "props": {
        "map": {
          "id": "td1",
          "kind": "mapbox_topdown",
          "src": "captures/topdown.jpg",
          "fps": null,
          "duration_s": null,
          "width": 2560,
          "height": 1440,
          "events": [
            {
              "t": 0.0,
              "name": "pin",
              "x": 1065.3,
              "y": 1100.6,
              "target": "p2",
              "label": "Quarry",
              "lat": 33.99917,
              "lng": 36.20028
            },
            {
              "t": 0.0,
              "name": "pin",
              "x": 1496.2,
              "y": 377.5,
              "target": "p1",
              "label": "Temple",
              "lat": 34.00667,
              "lng": 36.20333
            }
          ],
          "credits": [
            "© Mapbox © Maxar"
          ]
        },
        "lines": [
          {
            "from": "p2",
            "to": "p1"
          }
        ]
      },
      "cues": []
    },
    {
      "id": "s5",
      "from": 480,
      "durationInFrames": 60,
      "block": "SourceViewer",
      "props": {
        "page": {
          "id": "src1",
          "kind": "source",
          "src": "captures/page.png",
          "fps": null,
          "duration_s": null,
          "width": 2560,
          "height": 3000,
          "events": [
            {
              "t": 0.0,
              "name": "page",
              "url": "https://www.dainst.org/baalbek-report",
              "title": "Baalbek report"
            },
            {
              "t": 0.0,
              "name": "highlight",
              "box": [
                200.0,
                1500.0,
                1800.0,
                120.0
              ],
              "target": "quote"
            }
          ],
          "credits": [
            "Source page: dainst.org"
          ]
        },
        "evidence": {
          "id": "e1",
          "claim_id": "c1",
          "kind": "quantity",
          "statement": "The Stone of the Pregnant Woman weighs about 1,000 tonnes.",
          "source": {
            "url": "https://www.dainst.org/baalbek-report",
            "title": "Baalbek: the largest stone blocks of antiquity",
            "tier": 1,
            "license": "",
            "quote": "the block, measuring 19.6 m in length, is estimated to weigh 1,650 tonnes",
            "locator": "section 2"
          },
          "paper_anchor": "ev-01"
        }
      },
      "cues": [
        {
          "frame": 500,
          "do": "highlight",
          "target": "e1"
        }
      ]
    },
    {
      "id": "s6",
      "from": 540,
      "durationInFrames": 60,
      "block": "EvidenceCard",
      "props": {
        "evidence": {
          "id": "e1",
          "claim_id": "c1",
          "kind": "quantity",
          "statement": "The Stone of the Pregnant Woman weighs about 1,000 tonnes.",
          "source": {
            "url": "https://www.dainst.org/baalbek-report",
            "title": "Baalbek: the largest stone blocks of antiquity",
            "tier": 1,
            "license": "",
            "quote": "the block, measuring 19.6 m in length, is estimated to weigh 1,650 tonnes",
            "locator": "section 2"
          },
          "paper_anchor": "ev-01"
        },
        "image": {
          "id": "m1",
          "src": "media/plate.jpg",
          "license": "CC BY-SA 4.0",
          "attribution": "Smoke Test",
          "source_url": "https://commons.wikimedia.org/wiki/File:Smoke.jpg",
          "depicts": "a test pattern standing in for the stone",
          "markers": [
            {
              "id": "mk1",
              "box": [
                0.42,
                0.38,
                0.14,
                0.2
              ],
              "label": "1 PERSON"
            }
          ]
        }
      },
      "cues": [
        {
          "frame": 550,
          "do": "stamp",
          "target": "e1"
        }
      ]
    }
  ],
  "captions": [
    {
      "text": "THIS",
      "from": 12,
      "to": 24
    },
    {
      "text": "STONE",
      "from": 24,
      "to": 40
    },
    {
      "text": "WEIGHS",
      "from": 40,
      "to": 56
    },
    {
      "text": "ABOUT",
      "from": 56,
      "to": 70
    },
    {
      "text": "1,000",
      "from": 70,
      "to": 90
    },
    {
      "text": "TONNES.",
      "from": 90,
      "to": 110
    }
  ],
  "ticker": {
    "evidence": [
      {
        "frame": 0,
        "n": 0
      },
      {
        "frame": 480,
        "n": 1
      }
    ]
  },
  "chapters": [
    {
      "title": "The stone",
      "frame": 0
    },
    {
      "title": "On the globe",
      "frame": 150
    },
    {
      "title": "The evidence",
      "frame": 480
    }
  ],
  "credits": [
    {
      "sceneId": "s1",
      "text": "Photo: Smoke Test (CC BY-SA 4.0)"
    },
    {
      "sceneId": "s2",
      "text": "© Mapbox © OpenStreetMap © Maxar"
    },
    {
      "sceneId": "s2",
      "text": "© Mapbox © Maxar"
    },
    {
      "sceneId": "s4",
      "text": "© Mapbox © Maxar"
    },
    {
      "sceneId": "s5",
      "text": "Source page: dainst.org"
    },
    {
      "sceneId": "s6",
      "text": "Photo: Smoke Test (CC BY-SA 4.0)"
    }
  ],
  "thumbnails": [
    {
      "frame": 90,
      "text": "Who moved it?"
    },
    {
      "frame": 330,
      "text": "Where is Baalbek?"
    },
    {
      "frame": 440,
      "text": "How far apart?"
    }
  ]
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd video && npx vitest run test/smoke.test.ts && npx vitest run && npx tsc --noEmit`
Expected: `Tests  2 passed (2)`, then the whole suite `Test Files  24 passed (24)` / `Tests  203 passed (203)`, then no tsc output. (Task 37 adds `contract.test.ts` later: 25 files, 204 tests. Task 2's glyph review fix of 2026-09-27 added 3 tests to the 200 measured before.)

- [ ] **Step 5: Commit**

```bash
git add video/test/fixtures/smoke-timeline.json video/test/smoke.test.ts
git commit -m "Add the 10-second smoke timeline with every footage block" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 22: Local smoke render on the workstation (not CI)

No new files. This proves the whole renderer on the RTX 3080: the layout lint reports exactly the violations planted in Task 11's real-browser check (`npm run test:gpu`), HEVC NVENC clips decode, the layout lint is clean on the fixtures (the thumbnail teasers included), the chunked NVENC render joins frame-exactly, the three thumbnail candidates meet their limits, and every graphics block draws in a real Chrome: the smoke fixture carries the footage blocks, the demo timeline of Task 8 the twelve graphics blocks (ClaimBoard, EvidenceCard, Meter, QuoteCard, ScaleDrawing, UnitGrid, BarChart with a range bar, Timeline, Diagram, ListCard, ScaleZoom, ShareCard), which no other step renders before a real episode. It needs the workstation (NVIDIA driver, ffmpeg with `hevc_nvenc` on PATH); it writes only to `$TMP/studio-smoke`. The demo needs nothing in the public dir beyond the seven fonts. Tasks 22 and 36 are re-run on the finished code before the release (I8 step 1 of the build index), whatever ran earlier.

- [ ] **Step 1: Generate the fixture's assets** (the clips use the capture encoder settings of Task 25: `hevc_nvenc` on GPU 0, BT.709 limited range, `hvc1`)

```bash
S="$(cygpath -m "$TMP")/studio-smoke" && rm -rf "$S" && P="$S/public" && mkdir -p "$P/voice" "$P/captures" "$P/media" "$P/music" "$P/fonts" "$S/out"
F=ancient-nerds-map/public/fonts && cp $F/orbitron-600.woff2 $F/orbitron-700.woff2 $F/jetbrains-mono-400.woff2 $F/jetbrains-mono-500.woff2 $F/jetbrains-mono-400-latin-ext.woff2 $F/cormorant-garamond-400-latin.woff2 $F/cormorant-garamond-400-latin-ext.woff2 "$P/fonts/"
HEVC="-vf scale=out_color_matrix=bt709:out_range=tv,format=yuv420p -c:v hevc_nvenc -gpu 0 -preset p5 -tune hq -rc vbr -cq 16 -b:v 0 -bf 0 -g 60 -tag:v hvc1 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv -movflags +faststart -an"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=1600x1200 -frames:v 1 -q:v 3 "$P/media/plate.jpg"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=2880x1620:rate=60 -t 4 $HEVC "$P/captures/platform.mp4"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=1920x1080:rate=60 -t 3 $HEVC "$P/captures/globe.mp4"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=2560x1440 -frames:v 1 -q:v 3 "$P/captures/topdown.jpg"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=2560x3000 -frames:v 1 "$P/captures/page.png"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "sine=frequency=220:duration=12:sample_rate=48000" -ac 2 "$P/music/bed.wav"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "sine=frequency=440:duration=2.5:sample_rate=32000" -c:a libmp3lame -b:a 128k "$P/voice/b01.mp3"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "sine=frequency=660:duration=3:sample_rate=32000" -c:a libmp3lame -b:a 128k "$P/voice/b02.mp3"
echo "$S"
```

Expected: no ffmpeg output, then the smoke directory (e.g. `C:/Users/<you>/AppData/Local/Temp/studio-smoke`).

- [ ] **Step 2: The real-browser lint check; then lint, render (two chunks, to exercise the join) and the three thumbnails of the smoke fixture; lint and render the demo timeline**

```bash
set -o pipefail
S="$(cygpath -m "$TMP")/studio-smoke" && T="$(pwd -W)/video/test/fixtures/smoke-timeline.json"
cd video && npm run test:gpu
node --import tsx scripts/lint.ts --timeline "$T" --public-dir "$S/public" --report "$S/out/lint.json" 2>&1 | grep -v '^bundle'
node --import tsx scripts/render.ts --timeline "$T" --public-dir "$S/public" --out "$S/out/smoke.mp4" --chunk-frames 300 2>&1 | grep -v -e '^bundle' -e '%$'
for k in 1 2 3; do node --import tsx scripts/still.ts --timeline "$T" --public-dir "$S/public" --out-dir "$S/out" --candidate $k 2>&1 | grep -v '^bundle'; done
D="$(pwd -W)/src/fixtures/demo-timeline.json"
node --import tsx scripts/lint.ts --timeline "$D" --public-dir "$S/public" 2>&1 | grep -v '^bundle'
node --import tsx scripts/render.ts --timeline "$D" --public-dir "$S/public" --out "$S/out/demo.mp4" 2>&1 | grep -v -e '^bundle' -e '%$'
ls "$S"
```

Expected: `npm run test:gpu` ends with `Test Files  1 passed (1)` and `Tests  3 passed (3)` (about 35 s, measured 2026-09-27; Task 11 Step 5). In Remotion's Chrome on the NVIDIA, with the brand fonts arriving late, the layout lint reports exactly the planted overflow, safe-area, control-zone and overlap lines, the one-frame teaser's overflow included, and nothing outside lint mode. So the `lint clean` lines below come from a gate that is shown to fire. Then (measured 2026-09-26: about 90 s, 90 s, 3 x 20 s, 40 s and 140 s) every browser of the node scripts prints `gpu: ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)`. The smoke lint prints `lint: 100 frames (every 6, scale 0.5)`, then `lint: thumbnail 1 (frame 90)`, `lint: thumbnail 2 (frame 330)` and `lint: thumbnail 3 (frame 440)`, each after its own `gpu:` line, and `lint clean: 103 frames checked`; the render two `gpu:` lines (one per part) and the path of `smoke.mp4`; each still `candidate K, frame F` (90, 330, 440) and its two thumbnail paths. The demo lint prints `lint: 370 frames (every 6, scale 0.5)`, the three thumbnail lines (frames 108, 200 and 300) and `lint clean: 373 frames checked`; the demo render one `gpu:` line and the path of `demo.mp4`. Every command exits 0 (`pipefail` makes a failing node step fail the pipe). Each script bundled into `$S/bundle` (next to `$S/public`) and removed it again, so `ls` lists only `out` and `public`; nothing new is left in `%TEMP%` under `remotion-webpack-bundle-*`.

- [ ] **Step 3: Check the outputs**

```bash
S="$(cygpath -m "$TMP")/studio-smoke/out"
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,nb_frames,has_b_frames,color_space,color_range,sample_rate -of compact "$S/smoke.mp4"
ls -l "$S"/thumbnail_*.png "$S"/thumbnail_*.jpg && for k in 1 2 3; do for f in thumbnail_${k}_3840.png thumbnail_${k}_1280.jpg; do ffprobe -v error -show_entries stream=width,height -of csv=p=0 "$S/$f"; done; done
ffmpeg -hide_banner -loglevel error -y -i "$S/smoke.mp4" -vf "select='eq(n\,90)+eq(n\,200)+eq(n\,330)+eq(n\,440)+eq(n\,520)+eq(n\,580)',scale=640:-1,tile=3x2" -frames:v 1 -fps_mode vfr "$S/sheet.jpg"
ffmpeg -hide_banner -loglevel error -y -i "$S/thumbnail_1_1280.jpg" -i "$S/thumbnail_2_1280.jpg" -i "$S/thumbnail_3_1280.jpg" -filter_complex "[0][1][2]hstack=3,scale=1920:-1" "$S/thumbs.jpg"
ffprobe -v error -show_entries stream=codec_name,nb_frames -of compact "$S/demo.mp4"
ffmpeg -hide_banner -loglevel error -y -i "$S/demo.mp4" -vf "select='eq(n\,150)+eq(n\,330)+eq(n\,510)+eq(n\,690)+eq(n\,870)+eq(n\,1050)+eq(n\,1230)+eq(n\,1410)+eq(n\,1590)+eq(n\,1770)+eq(n\,1830)+eq(n\,1900)+eq(n\,1950)+eq(n\,2020)+eq(n\,2190)',scale=640:-1,tile=5x3" -frames:v 1 -fps_mode vfr "$S/demo_sheet.jpg"
```

Expected: `stream|codec_name=h264|width=1920|height=1080|has_b_frames=0|color_range=tv|color_space=bt709|r_frame_rate=60/1|nb_frames=600` and `stream|codec_name=aac|sample_rate=48000|...`; six thumbnail files, `3840,2160` and `1280,720` for each candidate, every JPEG well under 2 MB (about 90 KB); `demo.mp4` `h264` with `nb_frames=2220` and its AAC stream. Open the sheets and look. `sheet.jpg`: the plate with its `1 PERSON` marker and hook caption, the platform clip with the credit line, the globe clip with the `BAALBEK` pin (drifting along its track) and lower third, the top-down frame with `QUARRY`/`TEMPLE` pins and their line, the source page with the glowing highlight, the evidence card with the typed quote and the `VERIFIED` stamp. `thumbs.jpg`: each candidate's frame with its teaser (`WHO MOVED IT?`, `WHERE IS BAALBEK?`, `HOW FAR APART?`) in upper case on dark glass at the top left, nothing in the bottom-right corner; the scene's credit line at the bottom left, left aligned: `Photo: Smoke Test (CC BY-SA 4.0)` on candidate 1 (the plate, scene s1) and `© Mapbox © Maxar` on candidate 3 (the top-down frame, scene s4); none on candidate 2 (the globe take, scene s3, which has no credits). `demo_sheet.jpg`, one frame per scene: the claim board, the evidence card with its stamps, the meter at 80/20, the quote card, the scale drawing, the unit grid of 80 buses, the bar chart with the Stone of the Pregnant Woman as a solid bar to 1,000 and an outline on to 1,650 labelled `1,000–1,650 T`, the timeline, the diagram, the list card, then four ScaleZoom frames (the small bar readable before the pull-back; then the small one a dot with its label while the Great Pyramid's bar still runs past the right edge; at the end the large bar fitted at 80 % of the width) and the share card.

- [ ] **Step 4: Clean up**

```bash
rm -rf "$(cygpath -m "$TMP")/studio-smoke"
```

No commit.


### Task 23: The capture manifest

**Files:**
- Create: `pipeline/studio/capture/__init__.py` (docstring only; Task 32 adds the exports), `pipeline/studio/capture/manifest.py`
- Create: `tests/pipeline/studio/capture/__init__.py` (empty file)
- Test: `tests/pipeline/studio/capture/test_capture_manifest.py`

Check C1 (plan C's `pipeline/studio/errors.py` and `config.py`) must print its five lines first. The capture-id pattern and the four capture kinds are imported from `pipeline.studio.config` (`CAPTURE_ID_RE`, `CAPTURE_KINDS`), their one definition, which plan C's `script.py` imports too (owner rule: never duplicate a utility). Every capture function returns the manifest `build_manifest` validates (contract D2 = plan C's C7); `CaptureError` is a `StudioError`, so plan C's CLI turns it into exit 2 with the message.

- [ ] **Step 1: Write the failing test**

Create the empty file `tests/pipeline/studio/capture/__init__.py` (zero bytes), then:

**`tests/pipeline/studio/capture/test_capture_manifest.py`** (complete file):

```python
"""The capture manifest contract (plan C C7; pipeline/studio/capture/manifest.py)."""

import subprocess

import pytest

from pipeline.studio.capture.manifest import (
    CaptureError,
    as_int,
    as_number,
    build_manifest,
    capture_id,
    event,
    require_kind,
    tool_failure,
)
from pipeline.studio.errors import StudioError

KEYS = {"id", "kind", "path", "fps", "duration_s", "width", "height", "events", "credits"}


@pytest.fixture
def episode(tmp_path):
    (tmp_path / "captures").mkdir()
    return tmp_path


def _media(episode, name="platform-01.mp4"):
    path = episode / "captures" / name
    path.write_bytes(b"x")
    return path


def _args(episode, **changes):
    args = {
        "episode_dir": episode,
        "cid": "platform-01",
        "kind": "platform",
        "path": _media(episode),
        "fps": 60,
        "duration_s": 10.0,
        "width": 1920,
        "height": 1080,
        "events": [],
        "credits": [],
    }
    args.update(changes)
    return args


def test_capture_errors_are_studio_errors():
    assert issubclass(CaptureError, StudioError)


def test_capture_id_is_a_safe_slug():
    assert capture_id({"id": "platform-01"}) == "platform-01"
    for bad in ("", "PF1", "../x", "a b", None, "x" * 49):
        with pytest.raises(CaptureError):
            capture_id({"id": bad})


def test_require_kind_checks_the_spec_kind():
    assert require_kind({"id": "g1", "kind": "globe"}, "globe") == "g1"
    with pytest.raises(CaptureError, match="takes kind 'globe', not 'globe-flyto'"):
        require_kind({"id": "g1", "kind": "globe-flyto"}, "globe")


def test_event_rounds_and_accepts_only_known_extras():
    assert event(1.23456, "place", x=100.04, y=20, target="p1", label="Baalbek") == {
        "t": 1.235,
        "name": "place",
        "x": 100.0,
        "y": 20.0,
        "target": "p1",
        "label": "Baalbek",
    }
    assert event(0, "pin", lat=33.999171234, lng=36.2)["lat"] == 33.999171
    assert event(0, "highlight", box=[1, 2, 3, 4])["box"] == [1.0, 2.0, 3.0, 4.0]
    with pytest.raises(CaptureError, match="unknown fields"):
        event(0, "x", colour="red")
    with pytest.raises(CaptureError, match=r"not \[x, y, w, h\]"):
        event(0, "x", box=[1, 2, 0, 4])


def test_a_place_event_keeps_its_pixel_in_every_frame():
    ev = event(3.5, "place", target="p1", x=960, y=540, track=[[960.04, 540], None, [961, 539.96]])
    assert ev["track"] == [[960.0, 540.0], None, [961.0, 540.0]]
    with pytest.raises(CaptureError, match=r"track point \[1\] is not \[x, y\]"):
        event(0, "place", track=[[1]])


def test_spec_values_must_be_numbers():
    assert (as_number(3, "zoom"), as_number(2.5, "zoom"), as_int(1280, "width")) == (3.0, 2.5, 1280)
    for bad in ("3", True, None, float("nan")):
        with pytest.raises(CaptureError, match="zoom must be a number"):
            as_number(bad, "zoom")
    with pytest.raises(CaptureError, match="width must be an integer"):
        as_int(1280.5, "width")


def test_a_failed_tool_names_itself_its_exit_code_and_its_stderr():
    exc = subprocess.CalledProcessError(
        1, ["C:/ffmpeg/bin/ffmpeg.exe", "-i", "x"], stderr="\nNo NVENC capable devices found\n"
    )
    assert str(tool_failure("g1", exc)) == (
        "g1: ffmpeg.exe failed (exit 1): No NVENC capable devices found"
    )


def test_a_clip_manifest_is_exactly_the_contract(episode):
    m = build_manifest(
        **_args(episode, duration_s=12.3456, events=[event(0.5, "search", x=10, y=20)])
    )
    assert set(m) == KEYS
    assert (m["path"], m["fps"], m["duration_s"]) == ("captures/platform-01.mp4", 60, 12.346)


def test_a_still_has_neither_fps_nor_duration(episode):
    m = build_manifest(
        **_args(
            episode,
            cid="td1",
            kind="mapbox_topdown",
            path=_media(episode, "td1.jpg"),
            fps=None,
            duration_s=None,
            width=2560,
            height=1441,
            events=[event(0, "pin", x=1, y=2)],
        )
    )
    assert (m["fps"], m["duration_s"], m["height"]) == (None, None, 1441)
    with pytest.raises(CaptureError, match="a clip has fps and duration_s, a still neither"):
        build_manifest(**_args(episode, fps=None, duration_s=2.0))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"kind": "globe-flyto"}, "unknown capture kind"),
        ({"width": 1921}, "must be even"),
        ({"fps": 0}, "must be positive"),
        ({"events": [event(5, "a"), event(1, "b")]}, "out of order"),
        ({"events": [event(99, "late")]}, "outside"),
        ({"credits": [" "]}, "empty credit"),
    ],
)
def test_build_manifest_rejects_defects(episode, changes, message):
    with pytest.raises(CaptureError, match=message):
        build_manifest(**_args(episode, **changes))


def test_media_must_exist_directly_in_captures(episode, tmp_path):
    elsewhere = tmp_path / "elsewhere.mp4"
    elsewhere.write_bytes(b"x")
    with pytest.raises(CaptureError, match="not directly inside"):
        build_manifest(**_args(episode, path=elsewhere))
    with pytest.raises(CaptureError, match="does not exist"):
        build_manifest(**_args(episode, path=episode / "captures" / "gone.mp4"))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_manifest.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'pipeline.studio.capture'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/__init__.py`** (complete file for now; Task 32 replaces it with the exporting version):

```python
"""Studio captures (spec 2026-09-26 section 4.5; plan C contract C7). See Task 32."""
```

**`pipeline/studio/capture/manifest.py`** (complete file):

```python
"""Capture manifests: the one shape every capture function returns (plan C contract C7).

    {"id", "kind", "path", "fps", "duration_s", "width", "height",
     "events": [{"t", "name", ...}], "credits": [...]}

``kind`` is the spec's kind (platform | globe | source | mapbox_topdown). Capture ids and
kinds come from pipeline.studio.config (CAPTURE_ID_RE, CAPTURE_KINDS: plan C's script check
uses the same two, so the patterns exist once). ``path`` is
POSIX, relative to the episode directory and directly under ``captures/`` (the render
step links it into the Remotion public dir under the same relative path). ``fps`` and
``duration_s`` are both numbers for a clip and both null for a still. ``events`` are in
seconds of the captured media; an event may carry ``x``/``y`` (media pixels), ``box``
([x, y, w, h] media pixels), ``target`` (a case-file id), ``label``, ``url``, ``title``,
``lat``/``lng`` and ``track`` (globe place events: the place's [x, y] in every frame from
the event to the end of the take, null while hidden). ``pipeline.studio.captures`` stores
the manifest as captures/<id>.json.

Every capture failure is a CaptureError (a StudioError: plan C's CLI exits 2 with the
message). Spec values are read through as_number/as_int, so a missing or mistyped value
is a CaptureError too, and tool_failure turns a failed ffmpeg/ffprobe run into one.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

from pipeline.studio.config import CAPTURE_ID_RE, CAPTURE_KINDS
from pipeline.studio.errors import StudioError
from pipeline.video.shorts_render import MAPBOX_CREDIT

CAPTURES_DIR = "captures"
EVENT_EXTRAS = frozenset(
    {"x", "y", "box", "target", "label", "url", "title", "lat", "lng", "track"}
)

# In-frame credits the renderer draws and the description lists.
CREDIT_MAPBOX_SATELLITE = MAPBOX_CREDIT  # satellite-v9: imagery only
CREDIT_MAPBOX_STREETS = "© Mapbox © OpenStreetMap © Maxar"  # satellite-streets-v12, the site's map


class CaptureError(StudioError):
    """A capture could not be made or its result is invalid. Never swallowed."""


def as_number(value: Any, where: str) -> float:
    """A spec value as a float; a string, a bool, None or a non-finite number is a CaptureError."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise CaptureError(f"{where} must be a number, got {value!r}")
    return float(value)


def as_int(value: Any, where: str) -> int:
    """A spec value that must be an integer (a JSON int, not a float or a bool)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CaptureError(f"{where} must be an integer, got {value!r}")
    return value


def tool_failure(cid: str, exc: subprocess.CalledProcessError) -> CaptureError:
    """ffmpeg or ffprobe failed: the tool, its exit code and the end of its stderr.

    pipeline.video.media runs them with capture_output, so without this the reason (for
    example "No NVENC capable devices found") would be lost behind a bare exit code.
    """
    tool = Path(str(exc.cmd[0])).name
    return CaptureError(
        f"{cid}: {tool} failed (exit {exc.returncode}): {(exc.stderr or '').strip()[-2000:]}"
    )


def capture_id(spec: dict[str, Any]) -> str:
    """The spec's id; it names the media file, so it must be a safe slug."""
    cid = spec.get("id")
    if not isinstance(cid, str) or not CAPTURE_ID_RE.fullmatch(cid):
        raise CaptureError(f"capture id {cid!r} must match {CAPTURE_ID_RE.pattern}")
    return cid


def require_kind(spec: dict[str, Any], kind: str) -> str:
    """The spec's id after checking that the spec is of `kind`."""
    cid = capture_id(spec)
    if spec.get("kind") != kind:
        raise CaptureError(
            f"{cid}: this capture function takes kind {kind!r}, not {spec.get('kind')!r}"
        )
    return cid


def media_path(episode_dir: Path, cid: str, suffix: str) -> Path:
    return episode_dir / CAPTURES_DIR / f"{cid}{suffix}"


def event(t: float, name: str, **extra: Any) -> dict[str, Any]:
    """One manifest event; unknown extra keys are a programming error."""
    unknown = set(extra) - EVENT_EXTRAS
    if unknown:
        raise CaptureError(f"event {name!r} has unknown fields {sorted(unknown)}")
    out: dict[str, Any] = {"t": round(float(t), 3), "name": name}
    for key in ("x", "y"):
        if key in extra:
            out[key] = round(float(extra[key]), 1)
    if "box" in extra:
        box = [round(float(v), 1) for v in extra["box"]]
        if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
            raise CaptureError(f"event {name!r}: box {extra['box']!r} is not [x, y, w, h]")
        out["box"] = box
    for key in ("target", "label", "url", "title"):
        if key in extra:
            out[key] = str(extra[key])
    for key in ("lat", "lng"):
        if key in extra:
            out[key] = round(float(extra[key]), 6)
    if "track" in extra:
        track: list[list[float] | None] = []
        for point in extra["track"]:
            if point is not None and len(point) != 2:
                raise CaptureError(f"event {name!r}: track point {point!r} is not [x, y]")
            track.append(None if point is None else [round(float(v), 1) for v in point])
        out["track"] = track
    return out


def build_manifest(
    *,
    episode_dir: Path,
    cid: str,
    kind: str,
    path: Path,
    fps: float | None,
    duration_s: float | None,
    width: int,
    height: int,
    events: list[dict[str, Any]],
    credits: list[str],
) -> dict[str, Any]:
    """Validate and assemble a manifest; raises CaptureError on any defect."""
    if kind not in CAPTURE_KINDS:
        raise CaptureError(f"unknown capture kind {kind!r}")
    captures = (episode_dir / CAPTURES_DIR).resolve()
    resolved = path.resolve()
    if resolved.parent != captures:
        raise CaptureError(f"{path} is not directly inside {captures}")
    if not resolved.is_file():
        raise CaptureError(f"{path} does not exist")
    if width <= 0 or height <= 0:
        raise CaptureError(f"{path}: bad size {width}x{height}")
    if (fps is None) != (duration_s is None):
        raise CaptureError(f"{path}: a clip has fps and duration_s, a still neither")
    if fps is not None and duration_s is not None:
        if fps <= 0 or duration_s <= 0:
            raise CaptureError(f"{path}: fps {fps} and duration {duration_s} must be positive")
        if width % 2 or height % 2:
            raise CaptureError(f"{path}: video size {width}x{height} must be even")
    end = duration_s if duration_s is not None else 0.0
    last = -math.inf
    for ev in events:
        if ev["t"] < last:
            raise CaptureError(f"{path}: events out of order at {ev}")
        if not 0 <= ev["t"] <= end + 1e-6:
            raise CaptureError(f"{path}: event {ev} outside 0..{end} s")
        last = ev["t"]
    if any(not isinstance(c, str) or not c.strip() for c in credits):
        raise CaptureError(f"{path}: empty credit in {credits!r}")
    return {
        "id": cid,
        "kind": kind,
        "path": resolved.relative_to(episode_dir.resolve()).as_posix(),
        "fps": fps,
        "duration_s": None if duration_s is None else round(duration_s, 3),
        "width": width,
        "height": height,
        "events": events,
        "credits": credits,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_manifest.py -m "not integration and not live_llm" -q -rs`
Expected: `16 passed`

- [ ] **Step 5: Lint gate** (see Ground rules). Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/__init__.py pipeline/studio/capture/manifest.py tests/pipeline/studio/capture/__init__.py tests/pipeline/studio/capture/test_capture_manifest.py
git commit -m "Start the capture package with the manifest every capture returns" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 24: The GPU rule on the capture side

**Files:**
- Create: `pipeline/studio/capture/gpu.py`
- Test: `tests/pipeline/studio/capture/test_capture_gpu.py`

Measured 2026-09-26 on the workstation: Chrome without flags (Playwright headed and headless, Puppeteer headed) reported `ANGLE (AMD, AMD Radeon(TM) Graphics ...)`; with `CHROMIUM_GPU_ARGS` all three reported `ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)`. So every capture launches Chrome with these flags and then proves the renderer; plan C's doctor gets the NVENC probe, the Windows GPU preference helpers for Remotion's headless shell (`doctor --fix-gpu`, spec 4.11) and `chrome_renderer()`, the renderer of a headless Chrome launched exactly as the captures launch it.

- [ ] **Step 1: Write the failing test**

**`tests/pipeline/studio/capture/test_capture_gpu.py`** (complete file):

```python
"""The capture side of the GPU rule (pipeline/studio/capture/gpu.py, spec 4.11)."""

import shutil
import subprocess
import sys
import types

import pytest

from pipeline.studio.capture import gpu
from pipeline.studio.capture.manifest import CaptureError

NVIDIA = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)"
AMD = "ANGLE (AMD, AMD Radeon(TM) Graphics (0x00001681) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def test_only_the_nvidia_passes():
    assert gpu.require_nvidia(NVIDIA, "take") == NVIDIA
    for other in (
        AMD,
        "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
        "ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "",
    ):
        with pytest.raises(CaptureError, match="not the NVIDIA GPU"):
            gpu.require_nvidia(other, "take")


def test_the_renderer_is_recorded_as_a_gpu_event():
    assert gpu.gpu_event(NVIDIA) == {"t": 0.0, "name": "gpu", "label": NVIDIA}


def test_chrome_gets_the_flags_that_put_it_on_the_nvidia():
    assert gpu.CHROMIUM_GPU_ARGS[0] == "--use-angle=d3d11"
    assert "--force_high_performance_gpu" in gpu.CHROMIUM_GPU_ARGS
    assert "UNMASKED_RENDERER_WEBGL" in gpu.RENDERER_JS


def test_nvenc_needs_the_driver_and_both_encoders(monkeypatch):
    monkeypatch.setattr(gpu.shutil, "which", lambda name: None)
    assert gpu.nvenc_problem() == "nvidia-smi not found: no NVIDIA driver, so no NVENC"
    monkeypatch.setattr(gpu.shutil, "which", lambda name: f"/bin/{name}")
    listing = " V....D h264_nvenc  NVIDIA NVENC H.264 encoder (codec h264)\n"
    monkeypatch.setattr(
        gpu.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=listing, stderr=""),
    )
    assert gpu.nvenc_problem() == f"{gpu.FFMPEG_BIN} lacks ['hevc_nvenc']"
    listing += " V....D hevc_nvenc  NVIDIA NVENC hevc encoder (codec hevc)\n"
    assert gpu.nvenc_problem() is None


def test_remotion_browser_is_the_headless_shell_in_node_modules(tmp_path):
    with pytest.raises(CaptureError, match="npx remotion browser ensure"):
        gpu.remotion_browser(tmp_path)
    exe = tmp_path / gpu.HEADLESS_SHELL
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"exe")
    assert gpu.remotion_browser(tmp_path) == exe


class _FakeKey:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_winreg(store, key_exists):
    def open_key(root, path):
        if not key_exists:
            raise FileNotFoundError(path)
        return _FakeKey(store)

    def query(key, name):
        if name not in key.store:
            raise FileNotFoundError(name)
        return key.store[name], 1

    def set_value(key, name, reserved, kind, value):
        key.store[name] = value

    return types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        REG_SZ=1,
        OpenKey=open_key,
        CreateKey=lambda root, path: _FakeKey(store),
        QueryValueEx=query,
        SetValueEx=set_value,
    )


def test_gpu_preference_reads_and_pins_the_high_performance_gpu(monkeypatch, tmp_path):
    exe = tmp_path / "chrome-headless-shell.exe"
    store: dict[str, str] = {}
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(store, key_exists=False))
    assert gpu.gpu_preference(exe) is None
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(store, key_exists=True))
    assert gpu.gpu_preference(exe) is None
    gpu.set_gpu_preference(exe)
    assert store == {str(exe): "GpuPreference=2;"}
    assert gpu.gpu_preference(exe) == "GpuPreference=2;"


@pytest.mark.skipif(shutil.which("nvidia-smi") is None, reason="no NVIDIA driver on this machine")
def test_the_doctor_probe_finds_chrome_on_the_nvidia():
    pytest.importorskip("playwright")
    assert gpu.require_nvidia(gpu.chrome_renderer(), "doctor").startswith("ANGLE (NVIDIA")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_gpu.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL with `ImportError: cannot import name 'gpu' from 'pipeline.studio.capture'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/gpu.py`** (complete file):

```python
"""The capture side of the studio's GPU rule (spec 2026-09-26 section 4.11).

The workstation is a hybrid laptop: the NVIDIA GeForce RTX 3080 Laptop GPU (the only
CUDA device, index 0) and an integrated AMD Radeon. Every Chrome the captures drive
runs with CHROMIUM_GPU_ARGS; without them Chrome draws on the AMD (measured
2026-09-26: Playwright headed and headless, Puppeteer headed all reported
"ANGLE (AMD, AMD Radeon(TM) Graphics ...)"). Each capture then reads the WebGL
renderer of the page it drives (RENDERER_JS) and require_nvidia() aborts unless it
names the NVIDIA. The renderer string is recorded in the manifest as the event
{"t": 0, "name": "gpu", "label": <renderer>} (gpu_event), because the manifest
contract (plan C C7) has no other free field.

Remotion's own browser (video/scripts) proves its renderer the same way; Remotion
takes no Chromium flags, so `python -m pipeline.studio doctor --fix-gpu` (plan C) can pin
its headless shell to the high-performance GPU through the per-app preference of Windows
(HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences, "GpuPreference=2;"), with
remotion_browser(), gpu_preference() and set_gpu_preference() below. nvenc_problem()
tells the doctor and the tests whether NVENC encodes can run here; chrome_renderer() is
the doctor's probe of the Chrome the captures drive.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pipeline.studio.capture.manifest import CaptureError, event
from pipeline.video.media import FFMPEG_BIN

CHROMIUM_GPU_ARGS = [
    "--use-angle=d3d11",
    "--force_high_performance_gpu",
    "--force-high-performance-gpu",
    "--enable-gpu-rasterization",
    "--ignore-gpu-blocklist",
]
RENDERER_JS = """() => {
  const canvas = document.createElement('canvas')
  const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
  if (!gl) return ''
  const info = gl.getExtension('WEBGL_debug_renderer_info')
  return info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : ''
}"""
NOT_NVIDIA = re.compile(r"AMD|Radeon|SwiftShader|Basic Render|llvmpipe|Intel", re.IGNORECASE)
GPU_PREFERENCES_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
HIGH_PERFORMANCE = "GpuPreference=2;"
HEADLESS_SHELL = Path(
    "node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/"
    "chrome-headless-shell.exe"
)


def require_nvidia(renderer: str, where: str) -> str:
    """The renderer string when it names the NVIDIA; anything else aborts the capture."""
    if "NVIDIA" not in renderer or NOT_NVIDIA.search(renderer):
        raise CaptureError(
            f"{where}: Chrome draws on {renderer or 'no WebGL renderer'!r}, not the NVIDIA GPU "
            "(spec 4.11); run `python -m pipeline.studio doctor`"
        )
    return renderer


def gpu_event(renderer: str) -> dict[str, Any]:
    """The manifest event that records which GPU drew the capture."""
    return event(0, "gpu", label=renderer)


def nvenc_problem() -> str | None:
    """Why NVENC encodes cannot run on this machine, or None when they can."""
    if shutil.which("nvidia-smi") is None:
        return "nvidia-smi not found: no NVIDIA driver, so no NVENC"
    if shutil.which(FFMPEG_BIN) is None:
        return f"{FFMPEG_BIN} not found on PATH"
    encoders = subprocess.run(
        [FFMPEG_BIN, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    missing = [name for name in ("h264_nvenc", "hevc_nvenc") if name not in encoders]
    return f"{FFMPEG_BIN} lacks {missing}" if missing else None


def remotion_browser(video_dir: Path) -> Path:
    """The Chrome headless shell Remotion renders with (downloaded into video/node_modules)."""
    exe = video_dir / HEADLESS_SHELL
    if not exe.is_file():
        raise CaptureError(
            f"{exe} does not exist: run `npx remotion browser ensure` in {video_dir}"
        )
    return exe


def gpu_preference(exe: Path) -> str | None:
    """The Windows per-app GPU preference of `exe` (e.g. "GpuPreference=2;"), or None."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, GPU_PREFERENCES_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, str(exe))
    except FileNotFoundError:
        return None
    return str(value)


def set_gpu_preference(exe: Path) -> None:
    """Pin `exe` to the high-performance GPU (the NVIDIA) for the current Windows user."""
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, GPU_PREFERENCES_KEY) as key:
        winreg.SetValueEx(key, str(exe), 0, winreg.REG_SZ, HIGH_PERFORMANCE)


def chrome_renderer() -> str:
    """The WebGL renderer of a headless Chrome launched as the captures launch it.

    The doctor's probe (plan C Task 26): ok when require_nvidia() accepts the string.
    """
    from playwright.sync_api import sync_playwright  # local-only dependency

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=CHROMIUM_GPU_ARGS)
        page = browser.new_page()
        page.goto("about:blank")
        renderer = str(page.evaluate(RENDERER_JS))
        browser.close()
    return renderer
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_gpu.py -m "not integration and not live_llm" -q -rs`
Expected on the workstation: `7 passed`. Without the NVIDIA driver or Playwright (CI): `6 passed, 1 skipped`.

- [ ] **Step 5: Lint gate.** Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/gpu.py tests/pipeline/studio/capture/test_capture_gpu.py
git commit -m "Prove every capture browser draws on the NVIDIA and expose the NVENC and GPU-preference checks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 25: Frames to HEVC clips on NVENC

**Files:**
- Create: `pipeline/studio/capture/encode.py`
- Test: `tests/pipeline/studio/capture/test_capture_encode.py`

Root cause (measured 2026-09-26, Remotion 4.0.529): `renderMedia` over any `h264_nvenc` clip timed out with `Timeout while extracting frame at time 0.1sec`, while stills of the same clips rendered. `h264_nvenc` writes no VUI `bitstream_restriction`, so Mediabunny (the decoder behind `@remotion/media`) infers `num_reorder_frames` = MaxDpbFrames, up to 16 (`mediabunny/.../codec-data.js`), and Chrome's decoder holds its frames back. `libx264` writes `max_num_reorder_frames`, but a software encode is forbidden (spec 4.11); an HEVC SPS always carries `sps_max_num_reorder_pics`, and `hevc_nvenc` clips (1080p and 2880x1620, with and without B-frames) rendered cleanly. So clips are HEVC from `hevc_nvenc`. The capture frames are Chrome JPEGs (BT.601 full range, with an sRGB ICC profile that ffmpeg would carry as side data and that breaks `nb_frames` probing): the filter drops the profile and converts to the BT.709 limited range Mediabunny assumes; decoded back, pure red/green/blue stay within 4 levels. NVENC's smallest HEVC frame is above 64x36, so the tests use 256x144 frames. The encode tests need NVENC and skip with the reason elsewhere (CI).

- [ ] **Step 1: Write the failing test**

**`tests/pipeline/studio/capture/test_capture_encode.py`** (complete file):

```python
"""Captured frames -> constant-rate HEVC clips on NVENC (pipeline/studio/capture/encode.py)."""

import subprocess

import pytest

from pipeline.studio.capture.encode import (
    CLIP_ENCODE,
    CLIP_FILTER,
    concat_script,
    frames_to_cfr_mp4,
    sequence_length,
    sequence_to_mp4,
    take_seconds,
)
from pipeline.studio.capture.gpu import nvenc_problem
from pipeline.studio.capture.manifest import CaptureError
from pipeline.video.media import FFMPEG_BIN, FFPROBE_BIN, probe_frames

NVENC_PROBLEM = nvenc_problem()
needs_nvenc = pytest.mark.skipif(NVENC_PROBLEM is not None, reason=str(NVENC_PROBLEM))


def test_concat_script_gives_each_frame_its_real_duration():
    script = concat_script([10.0, 10.1, 10.25], end_ts=10.5, fps=60)
    assert script.splitlines() == [
        "ffconcat version 1.0",
        "file 'f000000.jpg'",
        "duration 0.100000",
        "file 'f000001.jpg'",
        "duration 0.150000",
        "file 'f000002.jpg'",
        "duration 0.250000",
        "file 'f000002.jpg'",
    ]


def test_last_frame_lasts_at_least_one_output_frame():
    assert "duration 0.016667" in concat_script([5.0], end_ts=5.0, fps=60)


def test_frames_play_in_timestamp_order_and_duplicates_are_dropped():
    script = concat_script([10.0, 10.2, 10.1, 10.1], end_ts=10.3, fps=60)
    assert script.splitlines()[1:] == [
        "file 'f000000.jpg'",
        "duration 0.100000",
        "file 'f000002.jpg'",
        "duration 0.100000",
        "file 'f000001.jpg'",
        "duration 0.100000",
        "file 'f000001.jpg'",
    ]


@pytest.mark.parametrize(
    ("timestamps", "end", "message"),
    [([], 1.0, "no frames"), ([1.0, 2.0], 1.5, "before the last frame")],
)
def test_concat_script_rejects_broken_takes(timestamps, end, message):
    with pytest.raises(CaptureError, match=message):
        concat_script(timestamps, end, 60)


def test_take_seconds_runs_from_the_first_frame_to_the_end():
    assert take_seconds([10.0, 10.5], 12.0, 60) == 2.0
    assert take_seconds([10.2, 10.0], 12.0, 60) == 2.0
    assert take_seconds([10.0], 10.0, 60) == pytest.approx(1 / 60)


def test_clips_are_hevc_on_nvenc_gpu_0_bt709_without_b_frames():
    def value(flag):
        return CLIP_ENCODE[CLIP_ENCODE.index(flag) + 1]

    assert (value("-c:v"), value("-gpu"), value("-bf"), value("-tag:v")) == (
        "hevc_nvenc",
        "0",
        "0",
        "hvc1",
    )
    assert (value("-colorspace"), value("-color_range")) == ("bt709", "tv")
    assert not any(arg in ("libx264", "libx265", "h264_nvenc") for arg in CLIP_ENCODE)
    assert "out_color_matrix=bt709" in CLIP_FILTER and "out_range=tv" in CLIP_FILTER
    assert CLIP_FILTER.startswith("sidedata=mode=delete:type=ICC_PROFILE,")


def test_sequence_length_refuses_gaps_and_strays(tmp_path):
    for i in (0, 1, 2):
        (tmp_path / f"f{i:06d}.jpg").write_bytes(b"x")
    assert sequence_length(tmp_path) == 3
    (tmp_path / "f000004.jpg").write_bytes(b"x")
    with pytest.raises(CaptureError, match="has gaps"):
        sequence_length(tmp_path)
    (tmp_path / "f000004.jpg").unlink()
    (tmp_path / "points.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CaptureError, match="not frames"):
        sequence_length(tmp_path)


def _frames(directory, count, icc=False):
    from PIL import Image, ImageCms

    # Chrome's canvas JPEGs carry an sRGB ICC profile, which ffmpeg keeps as stream side data.
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes() if icc else None
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for i in range(count):
        # NVENC's smallest HEVC frame is larger than 64x36; 256x144 is safely above it.
        image = Image.new("RGB", (256, 144), colours[i % 3])
        if profile is None:
            image.save(directory / f"f{i:06d}.jpg")
        else:
            image.save(directory / f"f{i:06d}.jpg", icc_profile=profile)


@needs_nvenc
def test_screencast_frames_become_a_constant_60fps_clip(tmp_path):
    _frames(tmp_path, 3)
    out = tmp_path / "clip.mp4"
    duration = frames_to_cfr_mp4(tmp_path, [0.0, 0.25, 0.5], end_ts=1.0, out=out, fps=60)
    assert duration == pytest.approx(1.0, abs=0.02)
    assert probe_frames(out) == 60


@needs_nvenc
def test_an_exact_sequence_keeps_every_frame_even_with_an_icc_profile(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    _frames(frames, 90, icc=True)
    assert sequence_to_mp4(frames, 60, tmp_path / "take.mp4") == 90
    assert probe_frames(tmp_path / "take.mp4") == 90
    stream = subprocess.run(
        [
            FFPROBE_BIN,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,codec_tag_string,color_space,color_range",
            "-of",
            "csv=p=0",
            str(tmp_path / "take.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert stream == "hevc,hvc1,tv,bt709"


@needs_nvenc
def test_colours_survive_the_bt709_conversion(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    _frames(frames, 3)
    sequence_to_mp4(frames, 60, tmp_path / "take.mp4")
    rgb = subprocess.run(
        [
            FFMPEG_BIN,
            "-v",
            "error",
            "-i",
            str(tmp_path / "take.mp4"),
            "-vf",
            "scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    frame = 256 * 144 * 3
    centre = (72 * 256 + 128) * 3
    red, green, blue = (rgb[i * frame + centre : i * frame + centre + 3] for i in range(3))
    assert red[0] > 240 and red[1] < 12 and red[2] < 12
    assert green[1] > 240 and green[0] < 12 and green[2] < 12
    assert blue[2] > 240 and blue[0] < 12 and blue[1] < 12
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_encode.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.studio.capture.encode'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/encode.py`** (complete file):

```python
"""Encoding captured frames into clips the renderer can decode.

Every clip is HEVC from hevc_nvenc on GPU 0 (spec 4.11: H.264/HEVC encodes run on
NVENC, never in software), BT.709 limited range, constant 60 fps, a keyframe every
second, no B-frames, `hvc1` tag, faststart. Not H.264: @remotion/media decodes a clip
with Chrome's VideoDecoder, and h264_nvenc writes no VUI bitstream_restriction, so
Mediabunny infers num_reorder_frames = MaxDpbFrames (up to 16, mediabunny
codec-data.js) and the decoder holds its frames back; every renderMedia over an
h264_nvenc clip timed out ("Timeout while extracting frame at time 0.1sec"), while
libx264 (which writes max_num_reorder_frames) and hevc_nvenc clips rendered
(measured 2026-09-26, Remotion 4.0.529, 1080p and 2880x1620). An HEVC SPS always
carries sps_max_num_reorder_pics (0 here). The capture frames are sRGB JPEGs (BT.601
full range once decoded, with Chrome's sRGB ICC profile attached): CLIP_FILTER drops
the profile and converts them to the BT.709 limited range the renderer's decoder
assumes, and the stream is tagged so.

Two sources:
* the platform take's CDP screencast: frames arrive at a variable rate with their own
  timestamps (frames_to_cfr_mp4 holds each frame until the next one);
* the recorder's exact frames (globe and Mapbox takes): one JPEG per output frame,
  f000000.jpg, f000001.jpg, ... (sequence_to_mp4).
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline.studio.capture.manifest import CaptureError
from pipeline.video.media import probe_duration, probe_frames, run_ffmpeg

CLIP_FILTER = (
    "sidedata=mode=delete:type=ICC_PROFILE,"
    "scale=in_color_matrix=bt601:in_range=pc:out_color_matrix=bt709:out_range=tv,"
    "format=yuv420p"
)
CLIP_ENCODE = [
    "-c:v",
    "hevc_nvenc",
    "-gpu",
    "0",
    "-preset",
    "p5",
    "-tune",
    "hq",
    "-rc",
    "vbr",
    "-cq",
    "16",
    "-b:v",
    "0",
    "-bf",
    "0",
    "-g",
    "60",
    "-pix_fmt",
    "yuv420p",
    "-tag:v",
    "hvc1",
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
    "-movflags",
    "+faststart",
    "-an",
]
FRAME_RE = re.compile(r"^f(\d{6})\.jpg$")


def concat_script(timestamps: list[float], end_ts: float, fps: int) -> str:
    """ffconcat list over the frames f<i:06>.jpg (i = arrival order, timestamps[i] its time).

    CDP frame timestamps are not strictly monotonic (two frames arrived 4.7 ms out of
    order in a real take, 2026-09-26), so the frames are played in timestamp order and a
    frame with the same timestamp as its predecessor is dropped. Each frame lasts until
    the next one; the last until `end_ts` (at least one output frame). The concat
    demuxer ignores the duration of the final entry, so the last file is listed twice.
    """
    if not timestamps:
        raise CaptureError("the screencast delivered no frames")
    ordered: list[tuple[float, int]] = []
    for ts, i in sorted((ts, i) for i, ts in enumerate(timestamps)):
        if not ordered or ts > ordered[-1][0]:
            ordered.append((ts, i))
    if end_ts < ordered[-1][0]:
        raise CaptureError(f"take end {end_ts} lies before the last frame {ordered[-1][0]}")
    lines = ["ffconcat version 1.0"]
    for k, (ts, i) in enumerate(ordered):
        nxt = ordered[k + 1][0] if k + 1 < len(ordered) else max(end_ts, ts + 1 / fps)
        lines.append(f"file 'f{i:06d}.jpg'")
        lines.append(f"duration {nxt - ts:.6f}")
    lines.append(f"file 'f{ordered[-1][1]:06d}.jpg'")
    return "\n".join(lines) + "\n"


def take_seconds(timestamps: list[float], end_ts: float, fps: int) -> float:
    """Length of the take from the earliest frame to its end (at least one output frame)."""
    return max(end_ts - min(timestamps), 1 / fps)


def frames_to_cfr_mp4(
    frames_dir: Path, timestamps: list[float], end_ts: float, out: Path, fps: int
) -> float:
    """Variable-rate screencast frames -> constant-rate clip; returns its duration in seconds.

    `-t` cuts the output at the take's end: the repeated last concat entry would
    otherwise add its duration a second time.
    """
    script = frames_dir / "frames.ffconcat"
    script.write_text(concat_script(timestamps, end_ts, fps), encoding="utf-8")
    seconds = take_seconds(timestamps, end_ts, fps)
    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(script),
            "-vf",
            f"fps={fps},{CLIP_FILTER}",
            "-t",
            f"{seconds:.6f}",
            *CLIP_ENCODE,
        ],
        out,
    )
    return probe_duration(out)


def sequence_length(frames_dir: Path) -> int:
    """Number of frames f000000.jpg .. f<n-1>.jpg; a gap or a stray file is an error."""
    names = sorted(p.name for p in frames_dir.iterdir())
    indices = [int(m.group(1)) for m in map(FRAME_RE.match, names) if m]
    if len(indices) != len(names):
        raise CaptureError(f"{frames_dir} holds files that are not frames")
    if indices != list(range(len(indices))):
        raise CaptureError(f"{frames_dir}: the frame sequence has gaps")
    return len(indices)


def sequence_to_mp4(frames_dir: Path, fps: int, out: Path) -> int:
    """Exact frames (one JPEG per output frame) -> constant-rate clip; returns the frame count."""
    count = sequence_length(frames_dir)
    if count == 0:
        raise CaptureError(f"{frames_dir} holds no frames")
    run_ffmpeg(
        [
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "f%06d.jpg"),
            "-vf",
            CLIP_FILTER,
            *CLIP_ENCODE,
        ],
        out,
    )
    encoded = probe_frames(out)
    if encoded != count:
        raise CaptureError(f"{out}: {encoded} frames encoded from {count}")
    return count
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_encode.py -m "not integration and not live_llm" -q -rs`
Expected on the workstation: `11 passed`. Without NVENC (CI): `8 passed, 3 skipped` with the reason (`nvidia-smi not found: no NVIDIA driver, so no NVENC`).

- [ ] **Step 5: Lint gate.** Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/encode.py tests/pipeline/studio/capture/test_capture_encode.py
git commit -m "Encode capture frames into constant-rate BT.709 HEVC clips on NVENC, which Remotion decodes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 26: Projection math for pins and globe poses

**Files:**
- Create: `pipeline/studio/capture/projection.py`
- Test: `tests/pipeline/studio/capture/test_capture_projection.py`

Web Mercator with 512-px tiles and bearing rotation (Mapbox GL and the Static API) puts top-down pins on their object; the globe model reproduces the site's telephoto camera (`latLngToPosition`, FOV 60° at distance 2.44 narrowing to 1.5° at 1.02) only to choose a pose that frames all places of a type-B shot inside `PLACES_BAND` (the part of the frame where GlobeShot's labels, drawn right of their pins, stay in the title-safe area above the captions and the player controls); the exact pin pixels come from the page (`window.__DEMO.screenPoint`, Task 34).

- [ ] **Step 1: Write the failing test**

**`tests/pipeline/studio/capture/test_capture_projection.py`** (complete file):

```python
"""Pure projection math of pipeline/studio/capture/projection.py."""

import math

import pytest

from pipeline.studio.capture.projection import (
    GLOBE_MAX_DISTANCE,
    PLACES_BAND,
    fit_globe_distance,
    globe_fov_deg,
    globe_to_pixel,
    mercator_to_pixel,
    mercator_world_px,
    meters_per_pixel,
    surface_point,
)


def test_mercator_world_origin_and_edges():
    assert mercator_world_px(0, 0, 0) == pytest.approx((256, 256))
    assert mercator_world_px(0, -180, 1)[0] == pytest.approx(0)
    assert mercator_world_px(0, 180, 1)[0] == pytest.approx(1024)


def test_mercator_rejects_polar_latitudes():
    with pytest.raises(ValueError, match="Web Mercator range"):
        mercator_world_px(89, 0, 3)


def test_centre_maps_to_the_middle_of_the_view():
    assert mercator_to_pixel(
        34.0, 36.2, center_lat=34.0, center_lng=36.2, zoom=15, bearing=0, width=1280, height=720
    ) == pytest.approx((640, 360))


def test_bearing_rotates_the_map_under_the_view():
    east = {"center_lat": 0.0, "center_lng": 0.0, "zoom": 10, "width": 1000, "height": 1000}
    x0, y0 = mercator_to_pixel(0.0, 0.01, bearing=0, **east)
    assert x0 > 500 and y0 == pytest.approx(500)
    x90, y90 = mercator_to_pixel(0.0, 0.01, bearing=90, **east)
    assert x90 == pytest.approx(500) and y90 < 500  # bearing 90 puts east at the top


def test_meters_per_pixel_at_the_equator():
    assert meters_per_pixel(0, 0) == pytest.approx(78271.517, rel=1e-6)
    assert meters_per_pixel(60, 1) == pytest.approx(78271.517 / 4, rel=1e-6)


def test_the_site_narrows_its_field_of_view_when_zoomed_in():
    assert globe_fov_deg(2.44) == pytest.approx(60)
    assert globe_fov_deg(1.02) == pytest.approx(1.5)
    assert globe_fov_deg(1.35) == pytest.approx(15.1, abs=0.05)
    with pytest.raises(ValueError, match="outside 1.02..2.44"):
        globe_fov_deg(3)


def test_surface_point_matches_the_frontend_mapping():
    assert surface_point(0, 0) == pytest.approx((1, 0, 0), abs=1e-12)
    assert surface_point(90, 0)[1] == pytest.approx(1)


def test_camera_target_projects_to_the_centre():
    px = globe_to_pixel(
        34.0, 36.2, cam_lat=34.0, cam_lng=36.2, distance=1.8, width=1920, height=1080
    )
    assert px == pytest.approx((960, 540), abs=1e-6)


def test_points_east_and_north_land_right_and_up():
    kw = {"cam_lat": 0.0, "cam_lng": 0.0, "distance": 2.0, "width": 1920, "height": 1080}
    east = globe_to_pixel(0.0, 10.0, **kw)
    north = globe_to_pixel(10.0, 0.0, **kw)
    assert east is not None and east[0] > 960 and east[1] == pytest.approx(540)
    assert north is not None and north[1] < 540 and north[0] == pytest.approx(960)


def test_the_telephoto_view_spreads_nearby_places():
    near = globe_to_pixel(
        33.0, 36.2, cam_lat=34.0, cam_lng=36.2, distance=1.35, width=1920, height=1080
    )
    far = globe_to_pixel(
        33.0, 36.2, cam_lat=34.0, cam_lng=36.2, distance=2.4, width=1920, height=1080
    )
    assert near is not None and far is not None
    assert near[1] - 540 > 3 * (far[1] - 540)


def test_far_side_is_not_visible_and_poles_are_refused():
    kw = {"cam_lat": 0.0, "cam_lng": 0.0, "distance": 2.0, "width": 1920, "height": 1080}
    assert globe_to_pixel(0.0, 180.0, **kw) is None
    with pytest.raises(ValueError, match="poles"):
        globe_to_pixel(0, 0, cam_lat=89, cam_lng=0, distance=2, width=10, height=10)


def test_fit_frames_every_place_inside_the_label_band():
    places = [(29.98, 31.13), (37.97, 23.73), (41.89, 12.49), (34.0, 36.2)]
    lat, lng, distance = fit_globe_distance(places, width=1920, height=1080)
    assert distance <= GLOBE_MAX_DISTANCE
    x0, y0, x1, y1 = PLACES_BAND
    for p_lat, p_lng in places:
        px = globe_to_pixel(
            p_lat, p_lng, cam_lat=lat, cam_lng=lng, distance=distance, width=1920, height=1080
        )
        assert px is not None
        assert 1920 * x0 <= px[0] <= 1920 * x1 and 1080 * y0 <= px[1] <= 1080 * y1


def test_fit_refuses_places_around_the_whole_globe():
    with pytest.raises(ValueError):
        fit_globe_distance([(0, 0), (0, 120), (0, -120)], width=1920, height=1080)
    with pytest.raises(ValueError, match="no places"):
        fit_globe_distance([], width=1920, height=1080)


def test_fit_centres_a_single_place():
    lat, lng, _ = fit_globe_distance([(34.0, 36.2)], width=1920, height=1080)
    assert lat == pytest.approx(34.0) and lng == pytest.approx(36.2)
    assert math.isfinite(lat)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_projection.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.studio.capture.projection'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/projection.py`** (complete file):

```python
"""Pure projection math for captures (spec 2026-09-26 section 4.5).

* Web Mercator with 512-px tiles, as Mapbox GL and the Static Images API use it:
  lat/lng -> pixel of an image with a given centre, zoom and bearing (top-down pins).
* Our Three.js globe: lat/lng -> pixel for the site's perspective camera at `distance`
  from the centre of the unit globe, looking at the centre, with the lat/lng mapping of
  latLngToPosition (ancient-nerds-map/src/utils/geoUtils.ts) and the site's telephoto
  field of view: 60 degrees at CAMERA.MAX_DISTANCE (2.44), narrowing linearly to 1.5
  degrees at CAMERA.MIN_DISTANCE (1.02) (Globe/rendering/animationLoop.ts). The places
  take reads the exact pixels from the page (window.__DEMO.screenPoint); this model only
  chooses a pose that frames all places.
"""

from __future__ import annotations

import math

TILE_SIZE = 512
EARTH_CIRCUMFERENCE_M = 40_075_016.686
# CAMERA.MIN_DISTANCE / MAX_DISTANCE of ancient-nerds-map/src/config/globeConstants.ts
CAMERA_MIN_DISTANCE = 1.02
CAMERA_MAX_DISTANCE = 2.44
FOV_AT_MAX_DEG = 60.0
FOV_RANGE_DEG = 58.5
# Studio globe takes stay at or above this distance: well outside
# CAMERA_EXTENDED.MAPBOX_ENABLE_DISTANCE (1.12), so no Mapbox tile is drawn.
GLOBE_MIN_DISTANCE = 1.2
GLOBE_MAX_DISTANCE = CAMERA_MAX_DISTANCE
# Where a lit place may sit in a 1920x1080 globe shot, as fractions (x0, y0, x1, y1): the
# renderer's GlobeShot draws each label to the right of its pin, and labels must stay in
# the title-safe area above the hook captions and the YouTube controls (the layout lint
# refused a label at y 946 of the first real places take, 2026-09-26).
PLACES_BAND = (0.12, 0.15, 0.78, 0.74)

Vec3 = tuple[float, float, float]


def mercator_world_px(lat: float, lng: float, zoom: float) -> tuple[float, float]:
    """World pixel of a point at `zoom` (world width TILE_SIZE * 2**zoom)."""
    if not -85.05112878 <= lat <= 85.05112878:
        raise ValueError(f"latitude {lat} outside the Web Mercator range")
    world = TILE_SIZE * 2**zoom
    x = (lng + 180.0) / 360.0 * world
    phi = math.radians(lat)
    y = (1 - math.log(math.tan(phi) + 1 / math.cos(phi)) / math.pi) / 2 * world
    return x, y


def mercator_to_pixel(
    lat: float,
    lng: float,
    *,
    center_lat: float,
    center_lng: float,
    zoom: float,
    bearing: float,
    width: float,
    height: float,
) -> tuple[float, float]:
    """Pixel of (lat, lng) in a width x height view centred on the centre point.

    Bearing is the compass direction at the top of the view (Mapbox), so the map is
    rotated counter-clockwise by `bearing` on screen.
    """
    cx, cy = mercator_world_px(center_lat, center_lng, zoom)
    px, py = mercator_world_px(lat, lng, zoom)
    dx, dy = px - cx, py - cy
    world = TILE_SIZE * 2**zoom
    if dx > world / 2:
        dx -= world
    elif dx < -world / 2:
        dx += world
    th = math.radians(-bearing)
    sx = dx * math.cos(th) - dy * math.sin(th)
    sy = dx * math.sin(th) + dy * math.cos(th)
    return width / 2 + sx, height / 2 + sy


def meters_per_pixel(lat: float, zoom: float) -> float:
    return EARTH_CIRCUMFERENCE_M * math.cos(math.radians(lat)) / (TILE_SIZE * 2**zoom)


def globe_fov_deg(distance: float) -> float:
    """The site's vertical field of view at a camera distance (the telephoto zoom)."""
    if not CAMERA_MIN_DISTANCE <= distance <= CAMERA_MAX_DISTANCE:
        raise ValueError(
            f"camera distance {distance} outside {CAMERA_MIN_DISTANCE}..{CAMERA_MAX_DISTANCE}"
        )
    zoom_t = (CAMERA_MAX_DISTANCE - distance) / (CAMERA_MAX_DISTANCE - CAMERA_MIN_DISTANCE)
    return FOV_AT_MAX_DEG - zoom_t * FOV_RANGE_DEG


def surface_point(lat: float, lng: float) -> Vec3:
    """latLngToPosition(lng, lat, 1) of the frontend."""
    phi = math.radians(90 - lat)
    theta = math.radians(lng + 180)
    return (-math.sin(phi) * math.cos(theta), math.cos(phi), math.sin(phi) * math.sin(theta))


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec3) -> Vec3:
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def globe_to_pixel(
    lat: float,
    lng: float,
    *,
    cam_lat: float,
    cam_lng: float,
    distance: float,
    width: float,
    height: float,
) -> tuple[float, float] | None:
    """Pixel of a surface point for the globe camera, or None on the far side of the globe."""
    if abs(cam_lat) > 85:
        raise ValueError(f"camera latitude {cam_lat}: lookAt degenerates near the poles")
    fov = globe_fov_deg(distance)
    cx, cy, cz = surface_point(cam_lat, cam_lng)
    cam = (cx * distance, cy * distance, cz * distance)
    point = surface_point(lat, lng)
    if _dot(point, cam) <= 1.0:
        return None
    forward = _norm((-cam[0], -cam[1], -cam[2]))
    right = _norm(_cross(forward, (0.0, 1.0, 0.0)))
    up = _cross(right, forward)
    v = (point[0] - cam[0], point[1] - cam[1], point[2] - cam[2])
    depth = _dot(v, forward)
    tan_half = math.tan(math.radians(fov) / 2)
    ndc_x = _dot(v, right) / (depth * tan_half * (width / height))
    ndc_y = _dot(v, up) / (depth * tan_half)
    return (ndc_x + 1) / 2 * width, (1 - ndc_y) / 2 * height


def fit_globe_distance(
    points: list[tuple[float, float]],
    *,
    width: float,
    height: float,
    band: tuple[float, float, float, float] = PLACES_BAND,
) -> tuple[float, float, float]:
    """Camera (lat, lng, distance) that shows every (lat, lng) inside `band` (fractions).

    The camera looks at the normalised mean of the surface points and moves out in
    0.02 steps from GLOBE_MIN_DISTANCE; raises when even GLOBE_MAX_DISTANCE cannot show
    them all (the places span too much of the globe for one shot).
    """
    if not points:
        raise ValueError("no places to frame")
    mean = [0.0, 0.0, 0.0]
    for lat, lng in points:
        p = surface_point(lat, lng)
        mean = [mean[i] + p[i] for i in range(3)]
    if math.sqrt(sum(c * c for c in mean)) < 1e-6:
        raise ValueError("places surround the globe; no single view shows them")
    c = _norm((mean[0], mean[1], mean[2]))
    cam_lat = math.degrees(math.asin(max(-1.0, min(1.0, c[1]))))
    cam_lng = math.degrees(math.atan2(c[2], -c[0])) - 180
    if cam_lng < -180:
        cam_lng += 360
    lo_x, lo_y, hi_x, hi_y = band[0] * width, band[1] * height, band[2] * width, band[3] * height
    steps = round((GLOBE_MAX_DISTANCE - GLOBE_MIN_DISTANCE) / 0.02)
    for i in range(steps + 1):
        d = round(GLOBE_MIN_DISTANCE + i * 0.02, 2)
        pixels = [
            globe_to_pixel(
                lat, lng, cam_lat=cam_lat, cam_lng=cam_lng, distance=d, width=width, height=height
            )
            for lat, lng in points
        ]
        if all(p is not None and lo_x <= p[0] <= hi_x and lo_y <= p[1] <= hi_y for p in pixels):
            return cam_lat, cam_lng, d
    raise ValueError(
        f"{len(points)} places do not fit one globe view (max distance {GLOBE_MAX_DISTANCE})"
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_projection.py -m "not integration and not live_llm" -q -rs`
Expected: `14 passed`

- [ ] **Step 5: Lint gate.** Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/projection.py tests/pipeline/studio/capture/test_capture_projection.py
git commit -m "Project places onto top-down frames and choose globe poses that frame every place" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 27: The workstation side: token, tools, an awake display, the local site

**Files:**
- Create: `pipeline/studio/capture/vite.py`
- Test: `tests/pipeline/studio/capture/test_capture_vite.py`
- Needs: check C1 (`config.REPO`); the base URL is `pipeline.utils.slugs.BASE_URL` (in the repo)

Root cause of the first failed Mapbox fly-in (2026-09-26, 11:41): the Windows display slept during the take, headed Chrome stopped producing animation frames and the first frame grab sat until Puppeteer's 15-minute protocol timeout. A re-run on an awake display completed. `display_awake()` holds the display on for a take (`SetThreadExecutionState`, as video players do); the recorder scenes bound every wait for an animation frame to 30 s (Task 35), so a display that stops drawing fails the take with that reason instead of hanging for 15 minutes. The local site is `npm run dev` with production data (`VITE_DEV_API_TARGET`) and `VIDEO_RECORD=1` (no hot reload mid-take).

- [ ] **Step 1: Write the failing test**

**`tests/pipeline/studio/capture/test_capture_vite.py`** (complete file):

```python
"""Token, tools, the awake display and the local site of the captures (capture/vite.py)."""

import os

import pytest

from pipeline.studio.capture import vite
from pipeline.studio.capture.manifest import CaptureError


def test_the_mapbox_token_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", " pk.test ")
    assert vite.require_mapbox_token() == "pk.test"
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "")
    with pytest.raises(CaptureError, match="loads the main checkout's .env"):
        vite.require_mapbox_token()


def test_a_missing_tool_is_named(monkeypatch):
    monkeypatch.setattr(vite.shutil, "which", lambda name: None)
    with pytest.raises(CaptureError, match="npm not found on PATH"):
        vite.require_tool("npm")


def test_the_frontend_lives_next_to_the_pipeline():
    assert (vite.FRONTEND_DIR / "package.json").is_file()
    assert (vite.FRONTEND_DIR / "video" / "record.ts").is_file()


def test_the_analytics_tracker_is_recognised_on_every_host():
    for url in ("https://ancientnerds.com/pulse.js", "http://localhost:5198/pulse.js?x=1"):
        assert vite.ANALYTICS_URL_RE.match(url), url
    for url in (
        "https://ancientnerds.com/data/sources.json",
        "https://ancientnerds.com/research/x",
    ):
        assert not vite.ANALYTICS_URL_RE.match(url), url


@pytest.mark.skipif(os.name != "nt", reason="SetThreadExecutionState exists only on Windows")
def test_display_awake_holds_the_display_for_the_take():
    with vite.display_awake():
        pass


@pytest.mark.skipif(os.name == "nt", reason="the refusal is for systems other than Windows")
def test_display_awake_refuses_other_systems():
    with pytest.raises(CaptureError, match="captures run on the Windows workstation"):
        with vite.display_awake():
            pass
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_vite.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL with `ImportError: cannot import name 'vite' from 'pipeline.studio.capture'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/vite.py`** (complete file):

```python
"""The workstation side of the captures: paths, the Mapbox token, tools, an awake
display and a local Vite dev server of the frontend.

Same setup as the Puppeteer recorder (ancient-nerds-map/video/record.ts): data and API
from production through VITE_DEV_API_TARGET, VIDEO_RECORD=1 so Vite neither watches
nor hot-reloads mid-take. Vite takes VITE_MAPBOX_ACCESS_TOKEN from the environment;
`python -m pipeline.studio` loads the main checkout's .env into it (config.load_env),
because a worktree has no .env of its own.

Headed Chrome draws only while the Windows display is on: when the display slept
during a recorder take (2026-09-26, the first studio-mapbox-flyin), no animation frame
came for 15 minutes and the take died on Puppeteer's protocol timeout. display_awake()
holds the display on for the length of a take (SetThreadExecutionState, as video
players do); if the display stops drawing anyway, the recorder scenes fail within 30 s
with that reason (ancient-nerds-map/video/scenes/studio-frames.ts).

The site's Umami tracker (/pulse.js, ancient-nerds-map/src/analytics) would count every
take of production, and every paper-page capture, as a human visitor: the Playwright
captures abort its request (ANALYTICS_URL_RE) before they load a page.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from pipeline.studio.capture.manifest import CaptureError
from pipeline.studio.config import REPO
from pipeline.utils.slugs import BASE_URL

FRONTEND_DIR = REPO / "ancient-nerds-map"
# The production site (target "production" of a platform take, our paper pages, the dev
# server's data and API): the repo's one definition of the public base URL.
PRODUCTION_URL = BASE_URL
# The Umami tracker script on any host (production or the local dev server).
ANALYTICS_URL_RE = re.compile(r"^https?://[^/]+/pulse\.js(\?.*)?$")
LOCAL_PORT = 5198
READY_TIMEOUT_S = 90
MAPBOX_ENV_VAR = "VITE_MAPBOX_ACCESS_TOKEN"
# SetThreadExecutionState flags (winbase.h)
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def require_mapbox_token() -> str:
    """The frontend's public Mapbox token from the environment."""
    token = os.environ.get(MAPBOX_ENV_VAR, "").strip()
    if not token:
        raise CaptureError(
            f"{MAPBOX_ENV_VAR} is not set: run the capture through `python -m pipeline.studio`, "
            "which loads the main checkout's .env"
        )
    return token


def require_tool(name: str) -> str:
    """Absolute path of a command on PATH."""
    path = shutil.which(name)
    if path is None:
        raise CaptureError(f"{name} not found on PATH; the capture needs it")
    return path


def kill_tree(proc: subprocess.Popen[bytes]) -> None:
    """Stop npm and its node child (child.kill() alone leaves Vite running on Windows)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False
        )
    else:
        proc.terminate()
    proc.wait(timeout=30)


@contextmanager
def display_awake() -> Iterator[None]:
    """Keep the Windows display and system awake for the block (headed Chrome needs it)."""
    if os.name != "nt":
        raise CaptureError("captures run on the Windows workstation (headed Chrome on the NVIDIA)")
    kernel32 = ctypes.windll.kernel32
    if not kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    ):
        raise CaptureError("SetThreadExecutionState refused to keep the display awake")
    try:
        yield
    finally:
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)


@contextmanager
def local_site(log_path: Path, port: int = LOCAL_PORT) -> Iterator[str]:
    """Run `npm run dev` on `port` for the duration of the block and yield its base URL."""
    npm = require_tool("npm")
    require_mapbox_token()
    env = {**os.environ, "VITE_DEV_API_TARGET": PRODUCTION_URL, "VIDEO_RECORD": "1"}
    url = f"http://localhost:{port}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        proc = subprocess.Popen(
            [npm, "run", "dev", "--", "--port", str(port), "--strictPort"],
            cwd=FRONTEND_DIR,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + READY_TIMEOUT_S
            while True:
                if proc.poll() is not None:
                    raise CaptureError(f"Vite exited with {proc.returncode}; see {log_path}")
                try:
                    if httpx.get(f"{url}/globe.html", timeout=2).status_code == 200:
                        break
                except httpx.TransportError:
                    pass  # not listening yet; the deadline below bounds the wait
                if time.monotonic() > deadline:
                    raise CaptureError(
                        f"Vite did not serve {url} within {READY_TIMEOUT_S} s; see {log_path}"
                    )
                time.sleep(0.5)
            yield url
        finally:
            kill_tree(proc)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_vite.py -m "not integration and not live_llm" -q -rs`
Expected on Windows: `5 passed, 1 skipped` (the refusal test is for other systems); on Linux the Windows test skips instead.

- [ ] **Step 5: Lint gate.** Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/vite.py tests/pipeline/studio/capture/test_capture_vite.py
git commit -m "Add the captures' workstation side: Mapbox token, tools, an awake display and the local Vite site" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 28: Exact top-down frames from the Mapbox Static API

**Files:**
- Create: `pipeline/studio/capture/mapbox.py`
- Test: `tests/pipeline/studio/capture/test_capture_mapbox.py`

The image is requested at @2x; each pin is placed with `mercator_to_pixel` for the same centre, zoom and bearing, so it sits on its object whatever the renderer's camera does (the owner verified such pins to within metres, 2026-09-26). Each pin must also sit in the band where its label stays readable after the renderer's cover fit, 8 % push and label placement (x 10-90 %, y 15-80 % of the frame): the layout lint refused both labels of the first real frame (zoom 15.6, pins at 94 % and 5 % of the height), so the capture refuses such a framing up front and says to move the centre or zoom out. The token is the frontend's public `VITE_MAPBOX_ACCESS_TOKEN`; no browser is involved, so no GPU proof. The HTTP call is faked in the tests.

- [ ] **Step 1: Write the failing test**

**`tests/pipeline/studio/capture/test_capture_mapbox.py`** (complete file):

```python
"""Mapbox Static top-down frames (pipeline/studio/capture/mapbox.py); the HTTP call is faked."""

import io

import httpx
import pytest

from pipeline.studio.capture import mapbox
from pipeline.studio.capture.manifest import CREDIT_MAPBOX_SATELLITE, CaptureError

SPEC = {
    "id": "td1",
    "kind": "mapbox_topdown",
    "center": {"lat": 34.0029, "lng": 36.2018},
    "zoom": 15.0,
    "bearing": 0,
    "style": "satellite-v9",
    "width": 1280,
    "height": 720,
    "pins": [
        {"id": "p2", "label": "Quarry", "lat": 33.99917, "lng": 36.20028},
        {"id": "p1", "label": "Temple of Jupiter", "lat": 34.00667, "lng": 36.20333},
    ],
}


def test_static_url_asks_for_the_exact_retina_view():
    assert mapbox.static_url(SPEC, "pk.test") == (
        "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/36.201800,34.002900,15.00,0.0,0/"
        "1280x720@2x?attribution=false&logo=false&access_token=pk.test"
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"center": {"lat": 34.0}}, "center must be"),
        ({"zoom": 23}, "zoom 23.0 outside"),
        ({"bearing": 360}, "bearing 360.0 outside"),
        ({"width": 1281}, "Static API limit"),
        ({"style": "dark-v11"}, "style 'dark-v11' not in"),
        ({"zoom": "15"}, "td1: zoom must be a number, got '15'"),
        ({"pitch": 30}, r"td1: unknown keys \['pitch'\]"),
    ],
)
def test_bad_views_are_rejected(changes, message):
    with pytest.raises(CaptureError, match=message):
        mapbox.static_url({**SPEC, **changes}, "pk.test")


def test_pins_are_projected_into_the_2x_image_with_label_and_coordinates():
    centre = {**SPEC, "pins": [{"id": "c", "label": "Centre", "lat": 34.0029, "lng": 36.2018}]}
    assert mapbox.pin_events(centre) == [
        {
            "t": 0.0,
            "name": "pin",
            "x": 1280.0,
            "y": 720.0,
            "target": "c",
            "label": "Centre",
            "lat": 34.0029,
            "lng": 36.2018,
        }
    ]
    events = mapbox.pin_events(SPEC)
    assert [e["target"] for e in events] == ["p2", "p1"]
    assert events[0]["y"] > 720 > events[1]["y"]  # the quarry lies south of the temple


def test_pins_off_the_frame_or_without_a_label_are_rejected():
    with pytest.raises(CaptureError, match="falls outside the frame"):
        mapbox.pin_events({**SPEC, "pins": [{"id": "far", "label": "x", "lat": 35.0, "lng": 36.2}]})
    # at zoom 15.6 the quarry sits at 94 % of the height: its label would go under the controls
    with pytest.raises(CaptureError, match=r"pin p2 sits at \(0\.42, 0\.94\) of the frame"):
        mapbox.pin_events({**SPEC, "zoom": 15.6})
    with pytest.raises(CaptureError, match=r"pins\[0\] must be"):
        mapbox.pin_events({**SPEC, "pins": [{"id": "p1", "lat": 34.0, "lng": 36.2}]})


class _Response:
    def __init__(self, content, content_type):
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None


def _jpeg(size):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, "gray").save(buf, "JPEG")
    return buf.getvalue()


def test_mapbox_topdown_writes_the_image_and_returns_a_still_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")
    calls = []
    monkeypatch.setattr(
        mapbox.httpx,
        "get",
        lambda url, timeout: calls.append(url) or _Response(_jpeg((2560, 1440)), "image/jpeg"),
    )
    manifest = mapbox.mapbox_topdown(tmp_path, SPEC)
    assert calls and "access_token=pk.test" in calls[0]
    assert manifest["path"] == "captures/td1.jpg" and (tmp_path / "captures" / "td1.jpg").is_file()
    assert (
        manifest["kind"],
        manifest["width"],
        manifest["height"],
        manifest["fps"],
        manifest["duration_s"],
    ) == (
        "mapbox_topdown",
        2560,
        1440,
        None,
        None,
    )
    assert manifest["credits"] == [CREDIT_MAPBOX_SATELLITE]
    assert not (tmp_path / "captures" / "td1.json").exists()  # pipeline.studio.captures stores it


def test_mapbox_topdown_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.delenv("VITE_MAPBOX_ACCESS_TOKEN", raising=False)
    with pytest.raises(CaptureError, match="VITE_MAPBOX_ACCESS_TOKEN"):
        mapbox.mapbox_topdown(tmp_path, SPEC)
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")
    monkeypatch.setattr(
        mapbox.httpx, "get", lambda url, timeout: _Response(_jpeg((1280, 720)), "image/jpeg")
    )
    with pytest.raises(CaptureError, match=r"expected \(2560, 1440\)"):
        mapbox.mapbox_topdown(tmp_path, SPEC)
    monkeypatch.setattr(
        mapbox.httpx, "get", lambda url, timeout: _Response(b"{}", "application/json")
    )
    with pytest.raises(CaptureError, match="not an image"):
        mapbox.mapbox_topdown(tmp_path, SPEC)


def test_a_refused_request_is_a_capture_error_without_the_token(tmp_path, monkeypatch):
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")

    class Unauthorized:
        def __init__(self, url):
            self.request = httpx.Request("GET", url)

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                f"Client error '401 Unauthorized' for url '{self.request.url}'",
                request=self.request,
                response=httpx.Response(401, request=self.request),
            )

    monkeypatch.setattr(mapbox.httpx, "get", lambda url, timeout: Unauthorized(url))
    with pytest.raises(CaptureError, match="td1: Mapbox Static API: Client error '401") as err:
        mapbox.mapbox_topdown(tmp_path, SPEC)
    assert "pk.test" not in str(err.value) and isinstance(
        err.value.__cause__, httpx.HTTPStatusError
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_mapbox.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL with `ImportError: cannot import name 'mapbox' from 'pipeline.studio.capture'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/mapbox.py`** (complete file):

```python
"""Exact top-down satellite frames from the Mapbox Static Images API with pins at their
projected pixels (spec 2026-09-26 section 4.5).

The image is requested at @2x (2 * width x 2 * height pixels); pins are placed with
projection.mercator_to_pixel for the same centre, zoom and bearing, so they sit on the
object whatever the renderer's camera does (the owner verified such pins to within
metres, 2026-09-26). The token is the frontend's public VITE_MAPBOX_ACCESS_TOKEN (the
Static API answers without a Referer, checked 2026-09-26). Pin ids are case-file place
ids and a pin's label is the case-file place's name (plan C binds both to the verified
case file); each pin event also carries its label and coordinates, from which the
renderer computes distance lines. Unknown spec keys, missing or non-numeric values and a refused
or failed request are CaptureErrors; no message carries the token.

Spec::

    {"id": "td1", "kind": "mapbox_topdown", "center": {"lat": 34.0022, "lng": 36.2018},
     "zoom": 16.1, "bearing": 0, "style": "satellite-v9", "width": 1280, "height": 720,
     "pins": [{"id": "p1", "label": "Quarry", "lat": 33.99917, "lng": 36.20028}, ...]}
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import httpx

from pipeline.studio.capture.manifest import (
    CREDIT_MAPBOX_SATELLITE,
    CREDIT_MAPBOX_STREETS,
    CaptureError,
    as_int,
    as_number,
    build_manifest,
    event,
    media_path,
    require_kind,
)
from pipeline.studio.capture.projection import mercator_to_pixel
from pipeline.studio.capture.vite import require_mapbox_token
from pipeline.utils.geo import is_valid_coordinates

STATIC_BASE = "https://api.mapbox.com/styles/v1/mapbox"
STYLES = {"satellite-v9": CREDIT_MAPBOX_SATELLITE, "satellite-streets-v12": CREDIT_MAPBOX_STREETS}
MAX_SIDE = 1280
RETINA = 2
# Where a pin may sit, as fractions of the frame: the renderer cover-fits the frame to
# 1920x1080, pushes in 8 % and puts each pin's label above or below it, so a pin outside
# this band sends its label out of the title-safe area or under the YouTube controls
# (the layout lint caught exactly that on the first real frame, 2026-09-26).
PIN_BAND_X = (0.10, 0.90)
PIN_BAND_Y = (0.15, 0.80)
SUFFIXES = {"image/jpeg": ".jpg", "image/png": ".png"}
SPEC_KEYS = frozenset(
    {"id", "kind", "center", "zoom", "bearing", "style", "width", "height", "pins"}
)


def _view(spec: dict[str, Any]) -> dict[str, Any]:
    cid = spec.get("id")
    unknown = set(spec) - SPEC_KEYS
    if unknown:
        raise CaptureError(f"{cid}: unknown keys {sorted(unknown)}")
    center = spec.get("center")
    if not isinstance(center, dict) or set(center) != {"lat", "lng"}:
        raise CaptureError(f"{cid}: center must be {{'lat': .., 'lng': ..}}, got {center!r}")
    lat = as_number(center["lat"], f"{cid}: center.lat")
    lng = as_number(center["lng"], f"{cid}: center.lng")
    if not is_valid_coordinates(lat, lng):
        raise CaptureError(f"{cid}: center {center!r} is not a coordinate")
    zoom = as_number(spec.get("zoom"), f"{cid}: zoom")
    bearing = as_number(spec.get("bearing", 0), f"{cid}: bearing")
    width = as_int(spec.get("width"), f"{cid}: width")
    height = as_int(spec.get("height"), f"{cid}: height")
    style = spec.get("style", "satellite-v9")
    if not 0 <= zoom <= 22:
        raise CaptureError(f"{cid}: zoom {zoom} outside 0..22")
    if not 0 <= bearing < 360:
        raise CaptureError(f"{cid}: bearing {bearing} outside 0..360")
    if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
        raise CaptureError(f"{cid}: {width}x{height} exceeds the Static API limit of {MAX_SIDE} px")
    if style not in STYLES:
        raise CaptureError(f"{cid}: style {style!r} not in {sorted(STYLES)}")
    return {
        "lat": lat,
        "lng": lng,
        "zoom": zoom,
        "bearing": bearing,
        "width": width,
        "height": height,
        "style": style,
    }


def static_url(spec: dict[str, Any], token: str) -> str:
    v = _view(spec)
    return (
        f"{STATIC_BASE}/{v['style']}/static/{v['lng']:.6f},{v['lat']:.6f},{v['zoom']:.2f},{v['bearing']:.1f},0/"
        f"{v['width']}x{v['height']}@2x?attribution=false&logo=false&access_token={token}"
    )


def pin_events(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """One "pin" event per pin with its pixel in the @2x image; a pin off the image is an error."""
    v = _view(spec)
    pins = spec.get("pins")
    if not isinstance(pins, list) or not pins:
        raise CaptureError(f"{spec['id']}: a top-down frame needs at least one pin")
    events = []
    for i, pin in enumerate(pins):
        if not isinstance(pin, dict) or set(pin) != {"id", "label", "lat", "lng"}:
            raise CaptureError(f"{spec['id']}: pins[{i}] must be {{id, label, lat, lng}}")
        lat = as_number(pin["lat"], f"{spec['id']}: pins[{i}].lat")
        lng = as_number(pin["lng"], f"{spec['id']}: pins[{i}].lng")
        x, y = mercator_to_pixel(
            lat,
            lng,
            center_lat=v["lat"],
            center_lng=v["lng"],
            zoom=v["zoom"],
            bearing=v["bearing"],
            width=v["width"],
            height=v["height"],
        )
        if not (0 <= x <= v["width"] and 0 <= y <= v["height"]):
            raise CaptureError(f"{spec['id']}: pin {pin['id']} falls outside the frame")
        fx, fy = x / v["width"], y / v["height"]
        if not (PIN_BAND_X[0] <= fx <= PIN_BAND_X[1] and PIN_BAND_Y[0] <= fy <= PIN_BAND_Y[1]):
            raise CaptureError(
                f"{spec['id']}: pin {pin['id']} sits at ({fx:.2f}, {fy:.2f}) of the frame, outside "
                f"the band x {PIN_BAND_X}, y {PIN_BAND_Y} where its label stays readable: "
                "move the centre or zoom out"
            )
        events.append(
            event(
                0,
                "pin",
                target=pin["id"],
                label=pin["label"],
                x=x * RETINA,
                y=y * RETINA,
                lat=lat,
                lng=lng,
            )
        )
    return events


def mapbox_topdown(episode_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Fetch one top-down frame into captures/<id>.jpg|.png and return its manifest (a still)."""
    from PIL import Image

    cid = require_kind(spec, "mapbox_topdown")
    token = require_mapbox_token()
    v = _view(spec)
    events = pin_events(spec)
    try:
        response = httpx.get(static_url(spec, token), timeout=30)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # httpx names the URL in its message, and the URL carries the token.
        raise CaptureError(f"{cid}: Mapbox Static API: {str(exc).replace(token, '***')}") from exc
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    if content_type not in SUFFIXES:
        raise CaptureError(f"{cid}: Static API answered {content_type!r}, not an image")
    width, height = v["width"] * RETINA, v["height"] * RETINA
    with Image.open(io.BytesIO(response.content)) as img:
        if img.size != (width, height):
            raise CaptureError(f"{cid}: Static API image is {img.size}, expected {(width, height)}")
    out = media_path(episode_dir, cid, SUFFIXES[content_type])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(response.content)
    return build_manifest(
        episode_dir=episode_dir,
        cid=cid,
        kind="mapbox_topdown",
        path=out,
        fps=None,
        duration_s=None,
        width=width,
        height=height,
        events=events,
        credits=[STYLES[v["style"]]],
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_mapbox.py -m "not integration and not live_llm" -q -rs`
Expected: `13 passed`

- [ ] **Step 5: Lint gate.** Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/mapbox.py tests/pipeline/studio/capture/test_capture_mapbox.py
git commit -m "Fetch exact top-down satellite frames with pins projected onto their objects" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 29: Source pages with the quote highlighted

**Files:**
- Create: `pipeline/studio/capture/sources.py`, `pipeline/studio/capture/highlight.js`
- Test: `tests/pipeline/studio/capture/test_capture_sources.py`
- Needs: check A2 (`EVIDENCE_ID_RE`) and check C1 (plan C Task 1's `config.check_slug`)

Playwright (Chrome channel, headless, with the NVIDIA flags and the renderer proof) loads the page at 1280 CSS px and device scale 2, hides fixed and sticky layers, wraps the quote in `<mark>` pieces across inline elements (a DOM Range) and shoots a window of 900 CSS px around it. The window is the viewport, resized and scrolled there, not a full-page screenshot: a full-page shot rasterises the whole page, and the 35,000 px Wikipedia article on Baalbek took 37 s on the GPU, past Playwright's 30 s timeout (measured 2026-09-26; the viewport shot takes 0.8 s). The highlight box is measured again after the resize. A page without the quote (paywall, login) fails with the advice to use a QuoteCard. On our own paper page (plan B's HTML contract) the first evidence id of a paragraph is the `<p id="ev-NN" class="theo-evidence">` itself, and every further id of that paragraph is an empty `<span class="theo-evidence-anchor" id="ev-NN">` (display block, height 0) inside it: the anchor mode outlines the paragraph for such a span, and a zero-size box is "no visible paragraph" rather than a green line. Anchors follow A, B and C: `ev-` and two or more digits, checked with plan A's `pipeline.lyra.theo_publishing.EVIDENCE_ID_RE` (contract C9: the one Python definition of the evidence-id format, applied with `fullmatch`), and the paper slug with plan C's `pipeline.studio.config.check_slug`; the module keeps no copy of either pattern (owner rule: never duplicate a utility, import it). A slug `check_slug` refuses becomes a `CaptureError` naming the capture. The manifest's width and height are read from the written PNG, never computed from the fractional CSS window. The page's Umami tracker is blocked, and a browser failure (a navigation timeout, a crashed page) is a `CaptureError` that carries Playwright's message; a venv without Playwright is a `CaptureError` before anything is written. The page's own `<title>` is recorded in the `page` event and drawn nowhere; its URL goes on screen only as the ASCII (IDNA) hostname without `www.` (`ascii_host`, the string `domainOf` draws in SourceViewer's address bar), in the credit `Source page: <host>`; and the highlighted quote only as pixels of the page image (owner decision 32: original quotes inside source screenshots are allowed). Plan C's capture step (its Task 20 `captures.py`) glyph-checks exactly the manifest's drawn strings (its credits and `place`/`pin` labels; D1), naming the capture, so a Greek, Hebrew or Chinese source page (a non-latin title, URL path or quote) passes. The highlight tests drive a local HTML file and, like the tests that fake the browser step, skip without Playwright (CI).

- [ ] **Step 1: Write the failing test**

**`tests/pipeline/studio/capture/test_capture_sources.py`** (complete file):

```python
"""Source and paper page captures (pipeline/studio/capture/sources.py, highlight.js)."""

import asyncio
import importlib.util

import pytest

from pipeline.studio.capture import sources
from pipeline.studio.capture.manifest import CaptureError
from pipeline.studio.capture.sources import (
    CONTEXT_PX,
    HIGHLIGHT_JS,
    ascii_host,
    capture_source,
    clip_window,
    image_box,
    source_target,
)

NVIDIA = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)"
QUOTE_SPEC = {
    "id": "src1",
    "kind": "source",
    "url": "https://x.org/a",
    "quote": "a long enough quote",
}


def test_source_target_for_a_source_and_for_our_paper():
    spec = {
        "id": "s1",
        "kind": "source",
        "url": "https://dainst.org/x",
        "quote": "the block weighs 1,650 tonnes",
    }
    assert source_target(spec) == ("https://dainst.org/x", "quote", "the block weighs 1,650 tonnes")
    paper = {"id": "p1", "kind": "source", "paper": "baalbek-stones", "anchor": "ev-07"}
    assert source_target(paper) == (
        "https://ancientnerds.com/research/baalbek-stones#ev-07",
        "anchor",
        "ev-07",
    )
    # plans A, B and C number evidence ev- plus two or more digits, so ev-100 and beyond exist
    assert source_target({**paper, "anchor": "ev-1234"})[2] == "ev-1234"


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        (
            {"id": "s1", "kind": "source", "url": "ftp://x.org/a", "quote": "a long enough quote"},
            "not an http",
        ),
        ({"id": "s1", "kind": "source", "url": "https://x.org/a", "quote": "short"}, "at least 12"),
        (
            {"id": "p1", "kind": "source", "paper": "Bad Slug", "anchor": "ev-07"},
            "p1: paper 'Bad Slug' is not a slug",
        ),
        ({"id": "p1", "kind": "source", "paper": "ok", "anchor": "ref-3"}, "evidence anchor"),
        # EVIDENCE_ID_RE is applied with fullmatch: a trailing newline is no evidence id
        ({"id": "p1", "kind": "source", "paper": "ok", "anchor": "ev-07\n"}, "evidence anchor"),
        (
            {"id": "x", "kind": "source", "url": "https://x.org/a"},
            "either url \\+ quote or paper \\+ anchor",
        ),
    ],
)
def test_source_target_rejects_bad_specs(spec, message):
    with pytest.raises(CaptureError, match=message):
        source_target(spec)


def test_capture_source_takes_only_source_specs(tmp_path):
    with pytest.raises(CaptureError, match="takes kind 'source'"):
        capture_source(tmp_path, {"id": "p1", "kind": "paper", "paper": "x", "anchor": "ev-01"})


def test_a_venv_without_playwright_is_a_capture_error(tmp_path, monkeypatch):
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *args: None if name == "playwright" else find_spec(name, *args),
    )
    with pytest.raises(CaptureError, match="src1: Playwright is not installed in this venv"):
        capture_source(tmp_path, QUOTE_SPEC)
    assert not (tmp_path / "captures").exists()


def test_clip_window_keeps_context_and_stays_on_the_page():
    assert clip_window({"x": 0, "y": 3000, "w": 500, "h": 60}, page_height=10_000) == (
        3000 - CONTEXT_PX,
        60 + 2 * CONTEXT_PX,
    )
    assert clip_window({"x": 0, "y": 100, "w": 500, "h": 60}, page_height=500) == (0.0, 500)


def test_image_box_is_in_captured_pixels():
    assert image_box({"x": 100, "y": 1000, "w": 300, "h": 40}, top=100) == [200, 1800, 600, 80]


def test_the_credit_names_the_ascii_host_that_sourceviewer_draws():
    # the same string as video/src/format.ts domainOf: IDNA (ASCII), without "www."
    assert ascii_host("https://www.dainst.org/baalbek?x=1") == "dainst.org"
    assert ascii_host("https://el.wikipedia.org/wiki/Κνωσός") == "el.wikipedia.org"
    assert ascii_host("https://bücher.example/x") == "xn--bcher-kva.example"


PAGE = """<!doctype html><html><head><title>Test source</title></head><body style="margin:0">
<div style="position:fixed;top:0;left:0;right:0;height:80px;background:red" id="cookie">We use cookies</div>
<p style="margin-top:1500px">Intro text.</p>
<p>The block, measuring <em>19.6&nbsp;m</em> in length, is estimated to weigh 1,650 tonnes.</p>
<p id="ev-07">Evidence paragraph.</p>
<p id="ev-02" class="theo-evidence"><span class="theo-evidence-anchor" id="ev-03" style="display:block;height:0"></span>Second evidence paragraph, anchored twice.</p>
</body></html>"""


def _run_highlight(tmp_path, mode, needle):
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    page_file = tmp_path / "page.html"
    page_file.write_text(PAGE, encoding="utf-8")

    async def go():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(page_file.as_uri())
            await page.add_script_tag(path=str(HIGHLIGHT_JS))
            await page.evaluate("() => window.__studio.hideOverlays()")
            box = await page.evaluate("([m, n]) => window.__studio.highlight(m, n)", [mode, needle])
            state = await page.evaluate(
                "() => ({marks: [...document.querySelectorAll('mark.__studio-hl')].map(m => m.textContent).join('|'),"
                " cookie: getComputedStyle(document.getElementById('cookie')).display})"
            )
            await browser.close()
            return box, state

    return asyncio.run(go())


def test_highlight_finds_a_quote_across_inline_elements(tmp_path):
    box, state = _run_highlight(
        tmp_path, "quote", "measuring 19.6 m in length, is estimated to weigh 1,650 TONNES"
    )
    assert box is not None and box["y"] > 1500 and box["w"] > 100
    assert state["marks"] == "measuring |19.6\xa0m| in length, is estimated to weigh 1,650 tonnes"
    assert state["cookie"] == "none"


def test_highlight_outlines_an_evidence_anchor_and_misses_absent_text(tmp_path):
    box, _ = _run_highlight(tmp_path, "anchor", "ev-07")
    assert box is not None and box["y"] > 1500
    missing, _ = _run_highlight(tmp_path, "quote", "text that is not on the page")
    assert missing is None


def test_a_second_evidence_id_outlines_its_whole_paragraph(tmp_path):
    # plan B puts the second and later ids of a paragraph on an empty, zero-height span
    span, _ = _run_highlight(tmp_path, "anchor", "ev-03")
    paragraph, _ = _run_highlight(tmp_path, "anchor", "ev-02")
    assert span is not None and span["h"] > 10 and span["w"] > 0
    assert span == paragraph


def test_the_manifest_size_is_the_size_of_the_written_png(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    from PIL import Image

    async def shot(url, mode, needle, out):
        # 906.3 CSS px at scale 2 is 1812.6; Chromium wrote a 1812 px tall PNG
        Image.new("RGB", (2560, 1812), "white").save(out)
        box = {"x": 100, "y": 1000, "w": 300, "h": 40}
        title = "Κνωσός - Βικιπαίδεια"
        return {"box": box, "top": 100, "height": 906.3, "title": title, "renderer": NVIDIA}

    monkeypatch.setattr(sources, "_capture", shot)
    manifest = capture_source(tmp_path, QUOTE_SPEC)
    assert (manifest["width"], manifest["height"]) == (2560, 1812)
    # the page's own <title> is a record in the page event; the drawn credit is the ASCII host
    assert manifest["credits"] == ["Source page: x.org"]
    assert manifest["events"][1]["title"] == "Κνωσός - Βικιπαίδεια"


def test_a_browser_failure_is_a_capture_error_with_its_cause(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.async_api")

    async def timeout(url, mode, needle, out):
        raise playwright.TimeoutError("Timeout 45000ms exceeded.")

    monkeypatch.setattr(sources, "_capture", timeout)
    with pytest.raises(CaptureError, match="src1: Timeout 45000ms exceeded.") as err:
        capture_source(tmp_path, QUOTE_SPEC)
    assert isinstance(err.value.__cause__, playwright.TimeoutError)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_sources.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.studio.capture.sources'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/highlight.js`** (complete file):

```js
// Page-side helpers of pipeline/studio/capture/sources.py, installed as window.__studio.
//   hideOverlays(): hide fixed/sticky layers (cookie bars, banners, sticky headers)
//   highlight(mode, needle): mode 'quote' finds the text (whitespace, quotes and
//     dashes normalised, case-insensitive, across inline elements) and wraps each
//     covered text piece in <mark class="__studio-hl">; mode 'anchor' outlines the
//     element with that id (our paper page's #ev-NN), or, when the id sits on an
//     empty span.theo-evidence-anchor (the second and later evidence ids of a
//     paragraph, plan B), the p.theo-evidence around it. Returns the highlight box
//     in page CSS pixels {x, y, w, h}, or null when nothing matches or the anchor
//     has no visible box.
//   box(): the current page box of the last highlight (after the viewport changed).
(() => {
  const NORMAL = { '‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', ' ': ' ' }
  const normalize = (s) => {
    let out = ''
    let space = true
    for (const raw of s) {
      const c = NORMAL[raw] ?? raw
      if (/\s/.test(c)) {
        if (!space) out += ' '
        space = true
      } else {
        out += c.toLowerCase()
        space = false
      }
    }
    return out.trim()
  }
  const unionBox = (rects) => {
    const xs = rects.flatMap((r) => [r.left, r.right])
    const ys = rects.flatMap((r) => [r.top, r.bottom])
    const x = Math.min(...xs)
    const y = Math.min(...ys)
    return { x: x + scrollX, y: y + scrollY, w: Math.max(...xs) - x, h: Math.max(...ys) - y }
  }
  let highlighted = []
  window.__studio = {
    hideOverlays() {
      for (const el of document.querySelectorAll('body *')) {
        const pos = getComputedStyle(el).position
        if (pos === 'fixed' || pos === 'sticky') el.style.setProperty('display', 'none', 'important')
      }
      document.documentElement.style.setProperty('overflow', 'visible', 'important')
      document.body.style.setProperty('overflow', 'visible', 'important')
    },
    highlight(mode, needle) {
      if (mode === 'anchor') {
        const hit = document.getElementById(needle)
        if (!hit) return null
        const el = hit.classList.contains('theo-evidence-anchor') ? hit.closest('p.theo-evidence') : hit
        if (!el) return null
        const box = unionBox([el.getBoundingClientRect()])
        if (box.w < 1 || box.h < 1) return null
        el.style.setProperty('outline', '4px solid #00cc66')
        el.style.setProperty('outline-offset', '6px')
        el.style.setProperty('background', 'rgba(0, 204, 102, 0.14)')
        highlighted = [el]
        return box
      }
      const style = document.createElement('style')
      style.textContent = 'mark.__studio-hl{background:rgba(0,204,102,.28);color:inherit;box-shadow:0 0 0 2px rgba(0,204,102,.9);border-radius:2px}'
      document.head.appendChild(style)
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
      let text = ''
      const map = []
      let space = true
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const s = node.textContent
        for (let i = 0; i < s.length; i++) {
          const c = NORMAL[s[i]] ?? s[i]
          if (/\s/.test(c)) {
            if (space) continue
            text += ' '
            space = true
          } else {
            text += c.toLowerCase()
            space = false
          }
          map.push([node, i])
        }
      }
      const q = normalize(needle)
      const at = text.indexOf(q)
      if (at < 0 || q.length === 0) return null
      const [startNode, startOffset] = map[at]
      const [endNode, endOffset] = map[at + q.length - 1]
      const range = document.createRange()
      range.setStart(startNode, startOffset)
      range.setEnd(endNode, endOffset + 1)
      const pieces = []
      const inRange = document.createTreeWalker(range.commonAncestorContainer.nodeType === 3 ? range.commonAncestorContainer.parentNode : range.commonAncestorContainer, NodeFilter.SHOW_TEXT)
      for (let node = inRange.nextNode(); node; node = inRange.nextNode()) {
        if (range.intersectsNode(node)) pieces.push(node)
      }
      const marks = []
      for (const node of pieces) {
        const s = node === startNode ? startOffset : 0
        const e = node === endNode ? endOffset + 1 : node.textContent.length
        if (e <= s) continue
        const middle = node.splitText(s)
        middle.splitText(e - s)
        const mark = document.createElement('mark')
        mark.className = '__studio-hl'
        middle.parentNode.insertBefore(mark, middle)
        mark.appendChild(middle)
        marks.push(mark)
      }
      highlighted = marks
      return unionBox(marks.flatMap((m) => [...m.getClientRects()]))
    },
    box() {
      if (highlighted.length === 0) return null
      return unionBox(highlighted.flatMap((m) => [...m.getClientRects()]))
    },
  }
})()
```

**`pipeline/studio/capture/sources.py`** (complete file):

```python
"""Source page captures for SourceViewer (spec 2026-09-26 section 4.5).

Loads the page in Chrome at 1280 CSS px wide with deviceScaleFactor 2, hides fixed and
sticky layers (cookie bars, banners, sticky headers), highlights the quote (a DOM Range
split into <mark> pieces, highlight.js) and screenshots a window of CONTEXT_PX CSS px
above and below it. The window is shot as the viewport, resized to it and scrolled
there: a full-page screenshot rasterises the whole page, and a 35,000 px Wikipedia
article took 37 s on the GPU, past Playwright's 30 s timeout (2026-09-26). Paywalled or login pages do not contain the quote, so the capture
fails with the advice to use a QuoteCard. The same code captures our own paper page
with its #ev-NN paragraph outlined (a second id of a paragraph is an empty span inside
it, plan B; highlight.js outlines the paragraph). The paper slug and the evidence id are
checked with the one definition of each (pipeline.studio.config.check_slug, plan C;
pipeline.lyra.theo_publishing.EVIDENCE_ID_RE, plan A's contract C9). The site's analytics
tracker is blocked (vite.ANALYTICS_URL_RE); a Playwright failure becomes a CaptureError
with its message, and the manifest's size is the size of the PNG Chromium wrote. The
page's own <title> is kept in the "page" event as a record and drawn nowhere (owner
decision 32); of the URL only the ASCII hostname is drawn (ascii_host: SourceViewer's
address bar and the credit "Source page: <host>"), so a Greek or Chinese source page
passes plan C's glyph check of the manifest's drawn strings (its glyphs.py).

Specs (kind "source")::

    {"id": "src-dai", "kind": "source", "url": "https://...", "quote": "verbatim sentence"}
    {"id": "paper-ev07", "kind": "source", "paper": "<paper slug>", "anchor": "ev-07"}

The manifest is a still with three events at t=0: "gpu" (the WebGL renderer that
proved Chrome runs on the NVIDIA, spec 4.11), "page" (url, title) and "highlight"
(box in image pixels, target "quote" or the anchor).
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pipeline.lyra.theo_publishing import EVIDENCE_ID_RE
from pipeline.studio.capture.gpu import CHROMIUM_GPU_ARGS, RENDERER_JS, gpu_event, require_nvidia
from pipeline.studio.capture.manifest import (
    CaptureError,
    build_manifest,
    event,
    media_path,
    require_kind,
)
from pipeline.studio.capture.vite import ANALYTICS_URL_RE, PRODUCTION_URL
from pipeline.studio.config import check_slug
from pipeline.studio.errors import StudioError

VIEWPORT = (1280, 800)
DEVICE_SCALE = 2
CONTEXT_PX = 900
SETTLE_MS = 1500
NAV_TIMEOUT_MS = 45_000
MIN_QUOTE_CHARS = 12
HIGHLIGHT_JS = Path(__file__).with_name("highlight.js")
# A desktop Chrome user agent: some sources serve bots a different page.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)


def source_target(spec: dict[str, Any]) -> tuple[str, str, str]:
    """(url, mode, needle) of a source spec; mode is 'quote' (a source) or 'anchor' (our paper)."""
    cid = spec.get("id")
    keys = set(spec) - {"id", "kind"}
    if keys == {"url", "quote"}:
        url = spec["url"]
        parsed = urlparse(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise CaptureError(f"{cid}: url {url!r} is not an http(s) URL")
        quote = spec["quote"]
        if not isinstance(quote, str) or len(quote.strip()) < MIN_QUOTE_CHARS:
            raise CaptureError(
                f"{cid}: quote must be at least {MIN_QUOTE_CHARS} characters of verbatim text"
            )
        return url, "quote", quote
    if keys == {"paper", "anchor"}:
        slug, anchor = spec["paper"], spec["anchor"]
        if not isinstance(slug, str):
            raise CaptureError(f"{cid}: paper {slug!r} is not a slug")
        try:
            check_slug(slug)
        except StudioError as exc:
            raise CaptureError(f"{cid}: paper {exc}") from exc
        if not isinstance(anchor, str) or not EVIDENCE_ID_RE.fullmatch(anchor):
            raise CaptureError(f"{cid}: anchor {anchor!r} is not an evidence anchor like ev-07")
        return f"{PRODUCTION_URL}/research/{slug}#{anchor}", "anchor", anchor
    raise CaptureError(
        f"{cid}: a source capture takes either url + quote or paper + anchor, got {sorted(keys)}"
    )


def clip_window(box: dict[str, float], page_height: float) -> tuple[float, float]:
    """(top, height) in CSS px of the screenshot window around the highlight."""
    top = max(0.0, box["y"] - CONTEXT_PX)
    bottom = min(page_height, box["y"] + box["h"] + CONTEXT_PX)
    if bottom <= top:
        raise CaptureError(f"empty capture window for box {box} on a {page_height}px page")
    return top, bottom - top


def ascii_host(url: str) -> str:
    """The hostname the video draws for a source page: ASCII (IDNA) without "www.", the
    same string as SourceViewer's address bar (video/src/format.ts domainOf)."""
    host = urlparse(url).hostname or ""
    return host.encode("idna").decode("ascii").removeprefix("www.")


def image_box(box: dict[str, float], top: float) -> list[float]:
    """Highlight box in pixels of the captured image."""
    return [
        box["x"] * DEVICE_SCALE,
        (box["y"] - top) * DEVICE_SCALE,
        box["w"] * DEVICE_SCALE,
        box["h"] * DEVICE_SCALE,
    ]


async def _capture(url: str, mode: str, needle: str, out: Path) -> dict[str, Any]:
    from playwright.async_api import async_playwright  # local-only dependency

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=CHROMIUM_GPU_ARGS)
        context = await browser.new_context(
            viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]},
            device_scale_factor=DEVICE_SCALE,
            user_agent=USER_AGENT,
        )
        # our own paper page must not count as a visit in the site's analytics
        await context.route(ANALYTICS_URL_RE, lambda route: route.abort())
        page = await context.new_page()
        renderer = require_nvidia(await page.evaluate(RENDERER_JS), "source capture")
        await page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_timeout(SETTLE_MS)
        await page.add_script_tag(path=str(HIGHLIGHT_JS))
        await page.evaluate("() => window.__studio.hideOverlays()")
        box = await page.evaluate(
            "([mode, needle]) => window.__studio.highlight(mode, needle)", [mode, needle]
        )
        if box is None and mode == "quote":
            raise CaptureError(
                f"quote not found on {url}; paywalled or login pages cannot be captured, use a QuoteCard"
            )
        if box is None:
            raise CaptureError(f"#{needle} has no visible paragraph on {url}")
        page_height = await page.evaluate("() => document.documentElement.scrollHeight")
        top, height = clip_window(box, page_height)
        await page.set_viewport_size({"width": VIEWPORT[0], "height": math.ceil(height)})
        await page.evaluate("(y) => window.scrollTo(0, y)", top)
        await page.wait_for_timeout(SETTLE_MS)
        scrolled = await page.evaluate("() => window.scrollY")
        box = await page.evaluate("() => window.__studio.box()")
        if not (scrolled <= box["y"] and box["y"] + box["h"] <= scrolled + height):
            raise CaptureError(f"{url}: the highlight left the capture window after scrolling")
        await page.screenshot(
            path=str(out),
            type="png",
            clip={"x": 0, "y": 0, "width": VIEWPORT[0], "height": height},
        )
        title = await page.title()
        await browser.close()
    return {"box": box, "top": scrolled, "height": height, "title": title, "renderer": renderer}


def capture_source(episode_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Capture one source page (or our paper page) into captures/<id>.png and return its manifest."""
    cid = require_kind(spec, "source")
    url, mode, needle = source_target(spec)
    if importlib.util.find_spec("playwright") is None:
        raise CaptureError(
            f"{cid}: Playwright is not installed in this venv "
            "(pip install playwright, then playwright install chrome)"
        )
    from PIL import Image
    from playwright.async_api import Error as PlaywrightError  # local-only, after validation

    out = media_path(episode_dir, cid, ".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        shot = asyncio.run(_capture(url, mode, needle, out))
    except PlaywrightError as exc:
        raise CaptureError(f"{cid}: {exc}") from exc
    # Chromium rounds the fractional CSS window to whole pixels its own way: measure the PNG.
    with Image.open(out) as img:
        width, height = img.size
    title = shot["title"].strip()
    # Our own paper page needs no credit. A source is credited by its ASCII host only: the
    # page's own <title> (often Greek, Hebrew, Chinese) stays a record in the page event.
    credits = [f"Source page: {ascii_host(url)}"] if mode == "quote" else []
    return build_manifest(
        episode_dir=episode_dir,
        cid=cid,
        kind="source",
        path=out,
        fps=None,
        duration_s=None,
        width=width,
        height=height,
        events=[
            gpu_event(shot["renderer"]),
            event(0, "page", url=url, title=title),
            event(
                0,
                "highlight",
                box=image_box(shot["box"], shot["top"]),
                target="quote" if mode == "quote" else needle,
            ),
        ],
        credits=credits,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_sources.py -m "not integration and not live_llm" -q -rs`
Expected on the workstation (Playwright and Chrome installed): `17 passed`. Without Playwright (CI): `12 passed, 5 skipped`.

- [ ] **Step 5: Lint gate.** Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/sources.py pipeline/studio/capture/highlight.js tests/pipeline/studio/capture/test_capture_sources.py
git commit -m "Capture source pages and our paper page with the quote highlighted, on the NVIDIA" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 30: Platform takes of the real site

**Files:**
- Create: `pipeline/studio/capture/platform.py`, `pipeline/studio/capture/nerv_cursor.js`
- Test: `tests/pipeline/studio/capture/test_capture_platform.py`

Playwright drives headed Chrome at 1920x1080 CSS px with device scale 2 on `globe.html?demo=1&video=1&hud=<scale>` (Task 33's capture mode) and records a CDP screencast (up to the display's pixel size: 2880x1620 on the workstation, 60 fps, measured 2026-09-26). The declarative actions are the spec's (`search`, `click_result`, `pause_rotation`, `fly_wait`, `open_details`, `measure`, `toggle_layer`, `wait`) plus the three the owner's platform moments need: `zoom` (the site's own zoom into Mapbox: clicking a search result only rotates the globe, `useFlyToAnimation.ts`, so the Measure moment needs it; the take scrolls the mouse wheel at the flown-to site until the zoom slider reads the percent), `proximity` (the Proximity tab: "set on globe", then a click on the place) and `filter` (spec 4.10 type B: a Filter panel mode, then a legend entry; `age` is a range slider without entries, so it is not a filter mode). `toggle_layer` refuses the Layers panel's `Satellite` base-map toggle in any case before anything starts (owner correction 2026-09-26: no satellite toggle in globe sections; satellite shows in the details page or a Mapbox take). The cursor is fast (0.25 s moves, paced against a deadline so slow CDP round trips never stretch a move; 45 ms keystrokes; owner rule: retention first) and drawn by the injected NERV cursor, because a screencast never contains the OS cursor. Measure and proximity points are clicked where the page draws them (`window.__DEMO.screenPoint`); two measure points less than 60 CSS px apart on screen refuse the take (the measurement would be noise: zoom in first). `hud` must lie in 0.5..2 (the page throws outside it and would never get ready). A page that is not ready within 120 s fails with the likely cause (production without the `?video=1` frontend), every other Playwright or ffmpeg failure becomes a `CaptureError` carrying its message, and the site's analytics tracker is blocked so a take of production is no visit. A take whose screencast delivers fewer than 24 frames per second while the cursor moves would stutter and fails; a screencast that delivered no frame at all (possible for a take without cursor moves, where the frame-rate check has nothing to measure) and a venv without Playwright are `CaptureError`s too, never a traceback. Frames and timestamps become a 60 fps HEVC clip; every action start is an event the renderer's virtual camera can follow.

- [ ] **Step 1: Write the failing test**

**`tests/pipeline/studio/capture/test_capture_platform.py`** (complete file):

```python
"""Planning logic of platform takes (pipeline/studio/capture/platform.py); the take needs headed Chrome."""

import asyncio
import importlib.util
import time
import types
from contextlib import nullcontext

import pytest

from pipeline.studio.capture import platform as platform_take
from pipeline.studio.capture.manifest import CaptureError
from pipeline.studio.capture.platform import (
    KEY_DELAY_MS,
    MAX_TAKE_S,
    MOVE_S,
    Take,
    _Driver,
    eased_path,
    events_from_marks,
    frame_size,
    measure_gap_ok,
    motion_fps,
    parse_zoom_percent,
    record_platform,
    screen_point_or_fail,
    take_url,
    validate_actions,
    wait_ready,
)


def test_validate_accepts_the_declarative_vocabulary():
    actions = [
        {"do": "pause_rotation"},
        {"do": "search", "q": "baalbek"},
        {"do": "click_result", "title": "Baalbek Stones"},
        {"do": "fly_wait", "s": 3},
        {"do": "zoom", "to": 90},
        {"do": "open_details", "title": "Baalbek Stones"},
        {"do": "measure", "a": {"lat": 34.0, "lng": 36.2}, "b": {"lat": 34.01, "lng": 36.21}},
        {"do": "toggle_layer", "label": "Empire Borders"},
        {"do": "proximity", "at": {"lat": 34.0067, "lng": 36.2033}},
        {"do": "filter", "mode": "category", "label": "Pyramid"},
        {"do": "wait", "s": 1.5},
    ]
    out = validate_actions(actions)
    assert [a["do"] for a in out] == [a["do"] for a in actions]
    assert out[3]["s"] == 3.0 and out[4]["to"] == 90
    assert out[8]["at"] == {"lat": 34.0067, "lng": 36.2033}
    assert out[9] == {"do": "filter", "mode": "category", "label": "Pyramid"}


@pytest.mark.parametrize(
    ("actions", "message"),
    [
        ([], "non-empty"),
        ([{"do": "scroll"}], "unknown action"),
        ([{"do": "search"}], r"needs exactly \['q'\]"),
        ([{"do": "search", "q": "x", "extra": 1}], "needs exactly"),
        ([{"do": "search", "q": " "}], "non-empty string"),
        ([{"do": "wait", "s": 0}], r"must be in \(0, 10\]"),
        ([{"do": "measure", "a": {"lat": 1}, "b": {"lat": 1, "lng": 2}}], "must be"),
        (
            [{"do": "measure", "a": {"lat": 91, "lng": 0}, "b": {"lat": 1, "lng": 2}}],
            "not a coordinate",
        ),
        ([{"do": "wait", "s": 10}] * 4, f"exceed the {MAX_TAKE_S:.0f} s take limit"),
        ([{"do": "wait", "s": "3"}], r"actions\[0\]\.s must be a number"),
        ([{"do": "zoom", "to": 101}], "zoom-slider percent 0..100"),
        ([{"do": "zoom", "to": 50.5}], r"actions\[0\]\.to must be an integer"),
        ([{"do": "proximity", "at": {"lat": 34.0}}], "must be"),
        ([{"do": "filter", "mode": "age", "label": "x"}], "mode must be one of"),
        # owner correction 2026-09-26: no satellite toggle in globe sections
        (
            [{"do": "toggle_layer", "label": " satellite "}],
            r"actions\[0\]: no satellite toggle in globe sections",
        ),
    ],
)
def test_validate_rejects_bad_actions(actions, message):
    with pytest.raises(CaptureError, match=message):
        validate_actions(actions)


def test_take_url_turns_on_demo_and_video_mode():
    assert (
        take_url("http://localhost:5198/", 1.3)
        == "http://localhost:5198/globe.html?demo=1&video=1&hud=1.3"
    )


def test_eased_path_is_fast_then_slow_and_ends_on_target():
    path = eased_path((0.0, 0.0), (100.0, 50.0), 15)
    assert len(path) == 15
    assert path[-1] == pytest.approx((100.0, 50.0))
    steps = [path[0][0]] + [b[0] - a[0] for a, b in zip(path, path[1:], strict=False)]
    assert steps == sorted(steps, reverse=True)


def test_measure_points_come_from_the_page_or_fail():
    where = {"lat": 34.0, "lng": 36.2}
    assert screen_point_or_fail({"x": 960, "y": 540}, "measure point a", where) == (960.0, 540.0)
    with pytest.raises(CaptureError, match="measure point b .* is not on screen"):
        screen_point_or_fail(None, "measure point b", {"lat": -34.0, "lng": -143.8})


def test_measure_points_need_room_on_screen():
    # a measurement between two clicks 50 px apart on the globe measures nothing: zoom in first
    assert measure_gap_ok((0.0, 0.0), (60.0, 0.0))
    assert not measure_gap_ok((100.0, 100.0), (130.0, 140.0))


def test_the_zoom_slider_reading_is_a_percent():
    assert (parse_zoom_percent("66%"), parse_zoom_percent(" 100 % ")) == (66, 100)
    with pytest.raises(CaptureError, match="not a percent"):
        parse_zoom_percent("Map")


def test_the_cursor_is_fast_even_when_each_move_takes_time():
    assert (MOVE_S, KEY_DELAY_MS) == (0.25, 45)

    class SlowMouse:
        """Each move blocks like a CDP round trip (5 ms)."""

        def __init__(self):
            self.times: list[float] = []

        async def move(self, x, y):
            time.sleep(0.005)
            self.times.append(time.time())

    page = types.SimpleNamespace(mouse=SlowMouse())
    driver = _Driver(page, Take())
    asyncio.run(driver.move(900.0, 500.0))
    started, _ended = driver.take.moves[0]
    assert page.mouse.times[-1] - started <= MOVE_S + 1 / 60
    assert driver.pos == (900.0, 500.0)


def test_events_are_relative_to_the_first_frame_in_media_pixels():
    marks = [(100.5, "search", {"x": 190.0, "y": 120.0}), (101.25, "fly_wait", {})]
    assert events_from_marks(marks, t0=100.0, scale=1.5) == [
        {"t": 0.5, "name": "search", "x": 285.0, "y": 180.0},
        {"t": 1.25, "name": "fly_wait"},
    ]


def test_motion_fps_is_the_worst_move():
    timestamps = [i / 60 for i in range(120)]
    assert motion_fps(timestamps, [(0.0, 0.5), (1.0, 1.5)]) == pytest.approx(62, abs=1)
    sparse = [0.0, 0.1, 0.2, 1.0, 1.25, 1.5]
    assert motion_fps(sparse, [(0.0, 0.5), (1.0, 1.5)]) == pytest.approx(6)
    assert motion_fps(sparse, []) == float("inf")


def test_record_platform_validates_before_starting_anything(tmp_path):
    with pytest.raises(CaptureError, match="takes kind 'platform'"):
        record_platform(tmp_path, {"id": "pf1", "kind": "globe"})
    base = {"id": "platform-01", "kind": "platform", "actions": [{"do": "pause_rotation"}]}
    with pytest.raises(CaptureError, match="target must be"):
        record_platform(tmp_path, {**base, "target": "staging"})
    with pytest.raises(CaptureError, match=r"unknown keys \['zoom'\]"):
        record_platform(tmp_path, {**base, "target": "local", "zoom": 2})
    with pytest.raises(CaptureError, match="unknown action"):
        record_platform(tmp_path, {**base, "target": "local", "actions": [{"do": "dance"}]})
    with pytest.raises(CaptureError, match=r"hud 3.0 outside 0.5..2.0"):
        record_platform(tmp_path, {**base, "target": "local", "hud": 3})
    with pytest.raises(CaptureError, match="hud must be a number"):
        record_platform(tmp_path, {**base, "target": "local", "hud": "1.3"})
    satellite = [{"do": "toggle_layer", "label": "Satellite"}]
    with pytest.raises(CaptureError, match="satellite shows in the details page or a Mapbox take"):
        record_platform(tmp_path, {**base, "target": "local", "actions": satellite})
    assert not (tmp_path / "captures").exists()


def test_frame_size_is_read_from_the_first_frame(tmp_path):
    from PIL import Image

    Image.new("RGB", (2880, 1620), "black").save(tmp_path / "f000000.jpg")
    assert frame_size(tmp_path) == (2880, 1620)


def test_a_page_that_never_gets_ready_names_the_likely_cause():
    playwright = pytest.importorskip("playwright.async_api")

    class NeverReady:
        async def wait_for_function(self, js, timeout):
            raise playwright.TimeoutError(f"Timeout {timeout}ms exceeded.")

    with pytest.raises(
        CaptureError,
        match=r"window.__VIDEO.ready not true within 120 s \(production needs the \?video=1 "
        r"frontend deployed; use target local\)",
    ):
        asyncio.run(wait_ready(NeverReady()))


def test_a_browser_failure_is_a_capture_error_with_its_cause(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.async_api")

    async def crash(base_url, hud, actions, frames_dir):
        raise playwright.TimeoutError("Timeout 10000ms exceeded.")

    monkeypatch.setattr(platform_take, "_record", crash)
    monkeypatch.setattr(platform_take, "display_awake", nullcontext)
    spec = {
        "id": "platform-01",
        "kind": "platform",
        "target": "production",
        "actions": [{"do": "pause_rotation"}],
    }
    with pytest.raises(CaptureError, match="platform-01: Timeout 10000ms exceeded.") as err:
        record_platform(tmp_path, spec)
    assert isinstance(err.value.__cause__, playwright.TimeoutError)


def test_a_venv_without_playwright_is_a_capture_error(tmp_path, monkeypatch):
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *args: None if name == "playwright" else find_spec(name, *args),
    )
    spec = {
        "id": "platform-01",
        "kind": "platform",
        "target": "local",
        "actions": [{"do": "pause_rotation"}],
    }
    with pytest.raises(CaptureError, match="platform-01: Playwright is not installed in this venv"):
        record_platform(tmp_path, spec)
    assert not (tmp_path / "captures").exists()


def test_a_screencast_without_frames_is_a_capture_error(tmp_path, monkeypatch):
    pytest.importorskip("playwright")

    async def no_frames(base_url, hud, actions, frames_dir):
        # a take without cursor moves: motion_fps has nothing to measure
        return Take()

    monkeypatch.setattr(platform_take, "_record", no_frames)
    monkeypatch.setattr(platform_take, "display_awake", nullcontext)
    spec = {
        "id": "platform-01",
        "kind": "platform",
        "target": "production",
        "actions": [{"do": "pause_rotation"}],
    }
    with pytest.raises(CaptureError, match="platform-01: the screencast delivered no frames"):
        record_platform(tmp_path, spec)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_platform.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.studio.capture.platform'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/nerv_cursor.js`** (complete file):

```js
// NERV cursor for studio platform takes (pipeline/studio/capture/platform.py).
// A CDP screencast never contains the OS cursor, so the take draws its own:
// a cyan ring that follows the mouse and a ripple on every click. Injected
// with context.add_init_script on ?demo=1&video=1 pages only.
(() => {
  const add = () => {
    if (document.getElementById('__nerv_cursor')) return
    const style = document.createElement('style')
    style.textContent = `
      #__nerv_cursor{position:fixed;left:-100px;top:-100px;width:26px;height:26px;margin:-13px 0 0 -13px;
        border:2px solid #20F0FF;border-radius:50%;box-shadow:0 0 10px #20F0FF,inset 0 0 6px rgba(32,240,255,.5);
        pointer-events:none;z-index:2147483647;transition:transform .08s}
      #__nerv_cursor::after{content:"";position:absolute;left:50%;top:50%;width:4px;height:4px;margin:-2px 0 0 -2px;
        background:#20F0FF;border-radius:50%}
      .__nerv_ripple{position:fixed;width:26px;height:26px;margin:-13px 0 0 -13px;border:2px solid #20F0FF;
        border-radius:50%;pointer-events:none;z-index:2147483646;animation:__nerv_rip .6s ease-out forwards}
      @keyframes __nerv_rip{to{transform:scale(3);opacity:0}}`
    document.head.appendChild(style)
    const cursor = document.createElement('div')
    cursor.id = '__nerv_cursor'
    document.body.appendChild(cursor)
    addEventListener('mousemove', (e) => {
      cursor.style.left = `${e.clientX}px`
      cursor.style.top = `${e.clientY}px`
    }, true)
    addEventListener('mousedown', (e) => {
      cursor.style.transform = 'scale(.75)'
      const ripple = document.createElement('div')
      ripple.className = '__nerv_ripple'
      ripple.style.left = `${e.clientX}px`
      ripple.style.top = `${e.clientY}px`
      document.body.appendChild(ripple)
      setTimeout(() => ripple.remove(), 700)
    }, true)
    addEventListener('mouseup', () => {
      cursor.style.transform = 'none'
    }, true)
  }
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', add)
  else add()
})()
```

**`pipeline/studio/capture/platform.py`** (complete file):

```python
"""Platform moments: a real take of ancientnerds.com (spec 2026-09-26 section 4.5).

Playwright drives Chrome (headed, GPU) at 1920x1080 CSS px with deviceScaleFactor 2; the
CDP screencast delivers frames up to the display's pixel size (2880x1620 on the
workstation, measured 2026-09-26), so the renderer's virtual camera can zoom to 1.5x
and stay sharp (PlatformClip refuses more). The manifest records the real frame size
and the events' x/y in those media pixels. The page runs in
``?demo=1&video=1&hud=<scale>``: panels hidden, HUD scaled, window.__VIDEO.ready at
globe_ready (ancient-nerds-map/src/utils/videoMode.ts). The cursor is fast on purpose
(retention, owner rule): 0.25 s moves, paced against a deadline so slow CDP round trips
never stretch them, and 45 ms keystrokes. Frames and their timestamps become a constant
60 fps clip (encode.frames_to_cfr_mp4); the start of every action goes into the
manifest's events, which the renderer's virtual camera can follow. Chrome runs with the
NVIDIA flags of gpu.py, and the take proves the GPU from the page's WebGL renderer
before the first frame (spec 4.11); the renderer string is the manifest's "gpu" event.
The display is held awake meanwhile, and the site's analytics tracker is blocked, so a
take of production counts as no visit.

Spec (kind "platform")::

    {"id": "platform-01", "kind": "platform", "target": "local" | "production", "hud": 1.3,
     "actions": [{"do": "pause_rotation"},
                 {"do": "search", "q": "baalbek"},
                 {"do": "click_result", "title": "Baalbek Stones"},
                 {"do": "fly_wait", "s": 3.0},
                 {"do": "zoom", "to": 90},
                 {"do": "open_details", "title": "Baalbek Stones"},
                 {"do": "measure", "a": {"lat": .., "lng": ..}, "b": {"lat": .., "lng": ..}},
                 {"do": "toggle_layer", "label": "Empire Borders"},
                 {"do": "proximity", "at": {"lat": .., "lng": ..}},
                 {"do": "filter", "mode": "country" | "category" | "source", "label": ".."},
                 {"do": "wait", "s": 1.0}]}

"hud" is optional (default 1.3, 0.5..2 as the page accepts). "zoom" scrolls the mouse
wheel at the centre of the view (the flown-to site) until the zoom slider reads "to"
percent; the app switches to Mapbox on its own. Measure and proximity points are clicked
where the page itself draws them (window.__DEMO.screenPoint), on the globe or on
Mapbox; measure points closer than MIN_MEASURE_GAP_PX on screen refuse the take.
"open_details" returns to the Search tab first (the result list shows only there).
"filter" clicks the Filter panel's mode button, then the legend entry named "label" (a
click toggles it). "toggle_layer" never takes the Satellite base map, in any case (owner
correction 2026-09-26: no satellite toggle in globe sections; satellite shows in the
details page or a Mapbox take): validate_actions refuses it before anything starts. Playwright is a local-only dependency (in no requirements file); it
is imported inside the take, after the spec is validated, and a venv without it is a
CaptureError.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import math
import re
import shutil
import subprocess
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pipeline.studio.capture.encode import frames_to_cfr_mp4
from pipeline.studio.capture.gpu import CHROMIUM_GPU_ARGS, RENDERER_JS, gpu_event, require_nvidia
from pipeline.studio.capture.manifest import (
    CREDIT_MAPBOX_STREETS,
    CaptureError,
    as_int,
    as_number,
    build_manifest,
    event,
    media_path,
    require_kind,
    tool_failure,
)
from pipeline.studio.capture.vite import (
    ANALYTICS_URL_RE,
    PRODUCTION_URL,
    display_awake,
    local_site,
)

VIEWPORT = (1920, 1080)
DEVICE_SCALE = 2
FPS = 60
HUD_SCALE = 1.3
# videoMode.ts HUD_MIN..HUD_MAX: outside it the page throws and never gets ready.
HUD_RANGE = (0.5, 2.0)
MOVE_S = 0.25
KEY_DELAY_MS = 45
LEAD_S = 0.5
TAIL_S = 0.6
MAX_TAKE_S = 30.0
# Frames per second the screencast must deliver while the cursor moves, or the fast cursor stutters.
MIN_MOTION_FPS = 24.0
READY_TIMEOUT_MS = 120_000
READY_JS = (
    "() => !!(window.__VIDEO && window.__VIDEO.ready && window.__DEMO"
    " && window.__DEMO.isReady && window.__DEMO.isReady())"
)
# Closer on screen, two measure clicks measure nothing a viewer can read.
MIN_MEASURE_GAP_PX = 60.0
ZOOM_WHEEL_PX = 100
ZOOM_STEP_S = 0.05
ZOOM_TIMEOUT_S = 8.0
START_POS = (620.0, 220.0)
CURSOR_JS = Path(__file__).with_name("nerv_cursor.js")
CHROME_ARGS = [
    *CHROMIUM_GPU_ARGS,
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--window-size=1940,1200",
]
CREDITS = [CREDIT_MAPBOX_STREETS]
# Filter panel modes with legend entries (FilterPanel.tsx; "age" is a range slider).
FILTER_BUTTONS = {"country": "Country", "category": "Category", "source": "Source"}
# The Layers panel's base-map toggle (MapLayersPanel.tsx) a take must never click: owner
# correction 2026-09-26, no satellite toggle in globe sections.
SATELLITE_LAYER = "satellite"

# action -> required keys (besides "do")
ACTIONS: dict[str, frozenset[str]] = {
    "pause_rotation": frozenset(),
    "search": frozenset({"q"}),
    "click_result": frozenset({"title"}),
    "fly_wait": frozenset({"s"}),
    "zoom": frozenset({"to"}),
    "open_details": frozenset({"title"}),
    "measure": frozenset({"a", "b"}),
    "toggle_layer": frozenset({"label"}),
    "proximity": frozenset({"at"}),
    "filter": frozenset({"mode", "label"}),
    "wait": frozenset({"s"}),
}


def _point(value: Any, where: str) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != {"lat", "lng"}:
        raise CaptureError(f"{where} must be {{'lat': .., 'lng': ..}}, got {value!r}")
    lat, lng = as_number(value["lat"], f"{where}.lat"), as_number(value["lng"], f"{where}.lng")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise CaptureError(f"{where}: ({lat}, {lng}) is not a coordinate")
    return {"lat": lat, "lng": lng}


def validate_actions(actions: Any) -> list[dict[str, Any]]:
    """Check the declarative action list; the planned waits must fit MAX_TAKE_S."""
    if not isinstance(actions, list) or not actions:
        raise CaptureError("a platform take needs a non-empty action list")
    out: list[dict[str, Any]] = []
    waits = 0.0
    for i, action in enumerate(actions):
        where = f"actions[{i}]"
        if not isinstance(action, dict) or action.get("do") not in ACTIONS:
            raise CaptureError(f"{where}: unknown action {action!r} (known: {sorted(ACTIONS)})")
        do = action["do"]
        keys = set(action) - {"do"}
        if keys != ACTIONS[do]:
            raise CaptureError(
                f"{where} ({do}) needs exactly {sorted(ACTIONS[do])}, got {sorted(keys)}"
            )
        clean: dict[str, Any] = {"do": do}
        for key in ("q", "title", "label"):
            if key in keys:
                if not isinstance(action[key], str) or not action[key].strip():
                    raise CaptureError(f"{where}.{key} must be a non-empty string")
                clean[key] = action[key]
        if do == "toggle_layer" and action["label"].strip().casefold() == SATELLITE_LAYER:
            raise CaptureError(
                f"{where}: no satellite toggle in globe sections (owner 2026-09-26): "
                "satellite shows in the details page or a Mapbox take"
            )
        if "s" in keys:
            s = as_number(action["s"], f"{where}.s")
            if not 0 < s <= 10:
                raise CaptureError(f"{where}.s must be in (0, 10], got {s}")
            clean["s"] = s
            waits += s
        if do == "zoom":
            to = as_int(action["to"], f"{where}.to")
            if not 0 <= to <= 100:
                raise CaptureError(f"{where}.to must be a zoom-slider percent 0..100, got {to}")
            clean["to"] = to
        if do == "measure":
            clean["a"] = _point(action["a"], f"{where}.a")
            clean["b"] = _point(action["b"], f"{where}.b")
        if do == "proximity":
            clean["at"] = _point(action["at"], f"{where}.at")
        if do == "filter":
            if action["mode"] not in FILTER_BUTTONS:
                raise CaptureError(
                    f"{where}.mode must be one of {sorted(FILTER_BUTTONS)}, got {action['mode']!r}"
                )
            clean["mode"] = action["mode"]
        out.append(clean)
    if waits > MAX_TAKE_S:
        raise CaptureError(
            f"planned waits of {waits:.1f} s exceed the {MAX_TAKE_S:.0f} s take limit"
        )
    return out


def take_url(base_url: str, hud: float) -> str:
    return f"{base_url.rstrip('/')}/globe.html?{urlencode({'demo': 1, 'video': 1, 'hud': hud})}"


def eased_path(
    start: tuple[float, float], end: tuple[float, float], steps: int
) -> list[tuple[float, float]]:
    """Mouse positions for one move, ease-out cubic; the last point is `end`."""
    if steps < 1:
        raise ValueError("steps must be >= 1")
    (x0, y0), (x1, y1) = start, end
    out = []
    for i in range(1, steps + 1):
        e = 1 - (1 - i / steps) ** 3
        out.append((x0 + (x1 - x0) * e, y0 + (y1 - y0) * e))
    return out


def frame_size(frames_dir: Path) -> tuple[int, int]:
    """Pixel size of the screencast frames. Chrome caps it at the display's pixel size
    (2880x1620 on the workstation, measured 2026-09-26), so it is read, never assumed."""
    from PIL import Image

    with Image.open(frames_dir / "f000000.jpg") as first:
        return first.size


def events_from_marks(
    marks: list[tuple[float, str, dict[str, Any]]], t0: float, scale: float
) -> list[dict[str, Any]]:
    """Manifest events from the driver's marks: seconds since the first frame, x/y in media pixels."""
    return [
        event(max(0.0, t - t0), name, **{k: v * scale for k, v in extra.items()})
        for t, name, extra in marks
    ]


def motion_fps(timestamps: list[float], windows: list[tuple[float, float]]) -> float:
    """Lowest frame rate the screencast delivered during any cursor move (inf without moves)."""
    rates = []
    for start, end in windows:
        frames = sum(1 for ts in timestamps if start <= ts <= end)
        rates.append(frames / (end - start))
    return min(rates, default=float("inf"))


def screen_point_or_fail(
    point: dict[str, Any] | None, name: str, where: dict[str, float]
) -> tuple[float, float]:
    """The page's pixel for a point the take clicks; a hidden or off-screen point fails the take."""
    if point is None:
        raise CaptureError(f"{name} {where} is not on screen in this view")
    return float(point["x"]), float(point["y"])


def measure_gap_ok(a_px: tuple[float, float], b_px: tuple[float, float]) -> bool:
    """Whether two measure clicks lie at least MIN_MEASURE_GAP_PX CSS px apart."""
    return math.dist(a_px, b_px) >= MIN_MEASURE_GAP_PX


def parse_zoom_percent(text: str) -> int:
    """The zoom slider's reading ("66%", ZoomControls.tsx) as an integer percent."""
    m = re.fullmatch(r"\s*(\d{1,3})\s*%\s*", text)
    if not m:
        raise CaptureError(f"the zoom slider reads {text!r}, not a percent")
    return int(m.group(1))


async def wait_ready(page: Any) -> None:
    """Wait until the page may be filmed; a page that never gets there names the likely cause."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout  # local-only dependency

    try:
        await page.wait_for_function(READY_JS, timeout=READY_TIMEOUT_MS)
    except PlaywrightTimeout as exc:
        raise CaptureError(
            f"window.__VIDEO.ready not true within {READY_TIMEOUT_MS // 1000} s (production needs "
            "the ?video=1 frontend deployed; use target local)"
        ) from exc


@dataclass
class Take:
    renderer: str = ""
    timestamps: list[float] = field(default_factory=list)
    marks: list[tuple[float, str, dict[str, Any]]] = field(default_factory=list)
    moves: list[tuple[float, float]] = field(default_factory=list)
    end_ts: float = 0.0


class _Driver:
    """Runs actions on the page with the fast NERV cursor."""

    def __init__(self, page: Any, take: Take) -> None:
        self.page = page
        self.take = take
        self.pos = START_POS

    def mark(self, name: str, **extra: Any) -> None:
        self.take.marks.append((time.time(), name, extra))

    async def move(self, x: float, y: float) -> None:
        """One eased move of MOVE_S: step k waits for its deadline, so slow round trips never add up."""
        steps = max(6, round(MOVE_S * FPS))
        start = time.time()
        for k, (px, py) in enumerate(eased_path(self.pos, (x, y), steps), start=1):
            await self.page.mouse.move(px, py)
            await asyncio.sleep(max(0.0, start + MOVE_S * k / steps - time.time()))
        self.take.moves.append((start, time.time()))
        self.pos = (x, y)

    async def click_at(self, x: float, y: float, name: str | None) -> None:
        """Move there and click; `name` marks the click as a manifest event (None: no event)."""
        if name is not None:
            self.mark(name, x=x, y=y)
        await self.move(x, y)
        await self.page.mouse.click(x, y)

    async def click_locator(self, locator: Any, name: str | None) -> None:
        await locator.wait_for(state="visible", timeout=10_000)
        box = await locator.bounding_box()
        if box is None:
            raise CaptureError(f"{name}: element has no box")
        await self.click_at(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, name)

    async def screen_point(self, name: str, where: dict[str, float]) -> tuple[float, float]:
        point = await self.page.evaluate(
            "([lat, lng]) => window.__DEMO.screenPoint(lat, lng)", [where["lat"], where["lng"]]
        )
        return screen_point_or_fail(point, name, where)

    async def search_tab(self) -> None:
        """Back to the Search tab: Measure and Proximity replace the result list (FilterPanel.tsx)."""
        tab = self.page.locator(".tab-btn", has_text="Search").first
        if "active" not in str(await tab.get_attribute("class")).split():
            await self.click_locator(tab, None)

    def result_item(self, title: str) -> Any:
        title_re = re.compile(rf"^\s*{re.escape(title)}\s*$")
        return self.page.locator(
            ".search-result-item", has=self.page.locator(".search-result-title", has_text=title_re)
        ).first

    def legend_item(self, mode: str, label: str) -> Any:
        """The Filter panel's legend entry named `label` in `mode` (FilterPanel.tsx)."""
        label_re = re.compile(rf"^\s*{re.escape(label)}\s*$")
        if mode == "country":
            # text badges and flag buttons both carry the country as their title
            return self.page.locator(".country-legend-list").get_by_title(label, exact=True).first
        if mode == "category":
            return self.page.locator(".category-legend-item", has_text=label_re).first
        return self.page.locator(
            ".source-legend-item", has=self.page.locator(".source-legend-name", has_text=label_re)
        ).first

    async def zoom_to(self, to: int) -> None:
        """Wheel at the centre of the view (the flown-to site) until the zoom slider reads `to` %."""
        cx, cy = VIEWPORT[0] / 2, VIEWPORT[1] / 2
        self.mark("zoom", x=cx, y=cy)
        await self.move(cx, cy)
        display = self.page.locator(".zoom-slider-top .zoom-percent-display")
        current = parse_zoom_percent(await display.inner_text())
        step = -ZOOM_WHEEL_PX if current < to else ZOOM_WHEEL_PX  # a negative deltaY zooms in
        deadline = time.monotonic() + ZOOM_TIMEOUT_S
        while current < to if step < 0 else current > to:
            if time.monotonic() > deadline:
                raise CaptureError(
                    f"zoom: the slider reads {current} %, not {to} %, after {ZOOM_TIMEOUT_S:.0f} s"
                )
            await self.page.mouse.wheel(0, step)
            await asyncio.sleep(ZOOM_STEP_S)
            current = parse_zoom_percent(await display.inner_text())

    async def run(self, action: dict[str, Any]) -> None:
        do = action["do"]
        page = self.page
        if do == "pause_rotation":
            self.mark(do)
            await page.evaluate("window.__DEMO.setAutoRotate(false)")
        elif do == "search":
            await self.click_locator(page.locator("input.search-input"), do)
            await page.keyboard.type(action["q"], delay=KEY_DELAY_MS)
        elif do == "click_result":
            await self.click_locator(
                self.result_item(action["title"]).locator(".search-result-main"), do
            )
        elif do == "zoom":
            await self.zoom_to(action["to"])
        elif do == "open_details":
            await self.search_tab()
            item = self.result_item(action["title"])
            await item.hover()
            await self.click_locator(item.locator(".search-result-info-btn"), do)
        elif do == "measure":
            await self.click_locator(page.locator(".tab-btn", has_text="Measure"), do)
            a = await self.screen_point("measure point a", action["a"])
            b = await self.screen_point("measure point b", action["b"])
            if not measure_gap_ok(a, b):
                raise CaptureError(
                    f"measure points a and b are {math.dist(a, b):.0f} px apart on screen; "
                    "zoom in first"
                )
            await self.click_at(*a, "measure_a")
            await self.click_at(*b, "measure_b")
        elif do == "toggle_layer":
            expand = page.locator('.layer-toggle-panel .panel-minimize-btn[title="Maximize"]')
            if await expand.count():
                await self.click_locator(expand.first, "expand_layers")
            label_re = re.compile(rf"^\s*{re.escape(action['label'])}\s*$")
            toggle = page.locator(
                ".layer-toggle-panel label.layer-toggle",
                has=page.locator(".layer-label", has_text=label_re),
            ).first
            await self.click_locator(toggle, do)
        elif do == "proximity":
            await self.click_locator(page.locator(".tab-btn", has_text="Proximity"), do)
            await self.click_locator(page.locator(".proximity-btn.set-on-globe"), None)
            x, y = await self.screen_point("proximity centre", action["at"])
            await self.click_at(x, y, "proximity_center")
        elif do == "filter":
            mode_button = page.locator(
                ".toggle-buttons .toggle-btn", has_text=FILTER_BUTTONS[action["mode"]]
            )
            await self.click_locator(mode_button.first, "filter_mode")
            await self.click_locator(self.legend_item(action["mode"], action["label"]), do)
        elif do in ("fly_wait", "wait"):
            self.mark(do)
            await asyncio.sleep(action["s"])
        else:
            raise CaptureError(f"unhandled action {do}")


async def _record(
    base_url: str, hud: float, actions: list[dict[str, Any]], frames_dir: Path
) -> Take:
    from playwright.async_api import async_playwright  # local-only dependency

    take = Take()
    pending: set[asyncio.Future[None]] = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=False, args=CHROME_ARGS)
        context = await browser.new_context(
            viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, device_scale_factor=DEVICE_SCALE
        )
        await context.add_init_script(path=str(CURSOR_JS))
        # a take of production must not count as a visit in the site's analytics
        await context.route(ANALYTICS_URL_RE, lambda route: route.abort())
        page = await context.new_page()
        await page.goto(take_url(base_url, hud), wait_until="load", timeout=90_000)
        await wait_ready(page)
        take.renderer = require_nvidia(await page.evaluate(RENDERER_JS), "platform take")
        cdp = await context.new_cdp_session(page)

        async def on_frame(params: dict[str, Any]) -> None:
            index = len(take.timestamps)
            (frames_dir / f"f{index:06d}.jpg").write_bytes(base64.b64decode(params["data"]))
            take.timestamps.append(float(params["metadata"]["timestamp"]))
            await cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})

        def handler(params: dict[str, Any]) -> None:
            task = asyncio.ensure_future(on_frame(params))
            pending.add(task)
            task.add_done_callback(pending.discard)

        cdp.on("Page.screencastFrame", handler)
        driver = _Driver(page, take)
        await page.mouse.move(*START_POS)
        await cdp.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 80,
                "maxWidth": VIEWPORT[0] * DEVICE_SCALE,
                "maxHeight": VIEWPORT[1] * DEVICE_SCALE,
                "everyNthFrame": 1,
            },
        )
        await asyncio.sleep(LEAD_S)
        for action in actions:
            await driver.run(action)
        await asyncio.sleep(TAIL_S)
        take.end_ts = time.time()
        await cdp.send("Page.stopScreencast")
        await asyncio.gather(*pending)
        await browser.close()
    return take


def record_platform(episode_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Record one platform take into captures/<id>.mp4 and return its manifest."""
    cid = require_kind(spec, "platform")
    if spec.get("target") not in ("local", "production"):
        raise CaptureError(
            f"{cid}: target must be 'local' or 'production', got {spec.get('target')!r}"
        )
    unknown = set(spec) - {"id", "kind", "target", "hud", "actions"}
    if unknown:
        raise CaptureError(f"{cid}: unknown keys {sorted(unknown)}")
    actions = validate_actions(spec.get("actions"))
    hud = as_number(spec.get("hud", HUD_SCALE), f"{cid}: hud")
    if not HUD_RANGE[0] <= hud <= HUD_RANGE[1]:
        raise CaptureError(
            f"{cid}: hud {hud} outside {HUD_RANGE[0]}..{HUD_RANGE[1]} (the page refuses it)"
        )
    if importlib.util.find_spec("playwright") is None:
        raise CaptureError(
            f"{cid}: Playwright is not installed in this venv "
            "(pip install playwright, then playwright install chrome)"
        )
    from playwright.async_api import Error as PlaywrightError  # local-only, after validation

    frames_dir = media_path(episode_dir, cid, ".frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    site = (
        local_site(media_path(episode_dir, cid, ".vite.log"))
        if spec["target"] == "local"
        else nullcontext(PRODUCTION_URL)
    )
    with display_awake(), site as base_url:
        try:
            take = asyncio.run(_record(base_url, hud, actions, frames_dir))
        except PlaywrightError as exc:
            raise CaptureError(f"{cid}: {exc}") from exc
    if not take.timestamps:
        raise CaptureError(f"{cid}: the screencast delivered no frames")
    smooth = motion_fps(take.timestamps, take.moves)
    if smooth < MIN_MOTION_FPS:
        raise CaptureError(
            f"{cid}: the screencast delivered {smooth:.1f} frames/s while the cursor moved "
            f"(< {MIN_MOTION_FPS}); the take would stutter"
        )
    width, height = frame_size(frames_dir)
    out = media_path(episode_dir, cid, ".mp4")
    try:
        duration = frames_to_cfr_mp4(frames_dir, take.timestamps, take.end_ts, out, FPS)
    except subprocess.CalledProcessError as exc:
        raise tool_failure(cid, exc) from exc
    shutil.rmtree(frames_dir)
    return build_manifest(
        episode_dir=episode_dir,
        cid=cid,
        kind="platform",
        path=out,
        fps=FPS,
        duration_s=duration,
        width=width,
        height=height,
        events=[
            gpu_event(take.renderer),
            *events_from_marks(take.marks, min(take.timestamps), width / VIEWPORT[0]),
        ],
        credits=CREDITS,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_platform.py -m "not integration and not live_llm" -q -rs`
Expected on the workstation: `30 passed`. Without Playwright (CI): `27 passed, 3 skipped` (the readiness, browser-failure and frameless-screencast tests).

- [ ] **Step 5: Lint gate.** Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/platform.py pipeline/studio/capture/nerv_cursor.js tests/pipeline/studio/capture/test_capture_platform.py
git commit -m "Record platform moments of the real site with the fast NERV cursor, on the NVIDIA" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 31: Globe and Mapbox takes through the recorder

**Files:**
- Create: `pipeline/studio/capture/globe.py`
- Test: `tests/pipeline/studio/capture/test_capture_globe.py`

`record_globe` validates the spec before any side effect (unknown keys per scene, every number typed and in range, `empire` a key of `EMPIRE_METADATA` because the frontend silently loads nothing for an unknown id, the places' `lead_s`/`interval_s` and their last light-up inside the take), writes the scene input to `captures/<id>.rec/input.json`, runs `npm run video:record -- <studio scene> --fps 60 --input ... --out ...` in the frontend with the display held awake, then checks what the scene wrote (Task 35): `renderer.json` must name the NVIDIA, the frame count must be exactly `floor(duration_s * 60 + 0.5)` (JS `Math.round`, as the scene counts; Python's `round()` rounds 304.5 to 304) and is checked before the encode, and `points.json` must hold one pixel (or null) per frame for every place. Places are projected per frame (owner rule): the scene reads `screenPoint` after every grabbed frame, and each `place` event starts at the first frame from its light-up time on where the page draws the place inside `PLACES_BAND` (the layout lint refused the Giza label of the first real places take, drawn at y 946 over the player controls) and carries its `track` to the end of the take, null where the place is hidden or leaves the band. A fixed pose is still fitted to the band (`sweep_lng_deg` 0); with a sweep the camera longitude runs from `cam_lng_from` by `sweep_lng_deg` over the take. The `distribution` scene is spec 4.10's world distribution: up to 500 places, labels optional, the whole globe in frame (distance 2.44) turning once (a sweep of 360 degrees from opposite the places' mean longitude). Every place gets its event the first time it faces the camera, and unlabelled places, which GlobeShot draws as dots without labels, are exempt from the band. The camera latitude is chosen before the take so that one turn can show every place: `distribution_pose` takes the latitude nearest the midpoint of the places' lowest and highest latitude (the midpoint itself or a whole degree within ±45) at which every place is admissible. A dot is admissible when it lies within the horizon less 5° (`|lat - cam_lat| <= acos(1/2.44) - 5`, 60.8°). A labelled place is admissible when projection.py's globe camera, the model `fit_globe_distance` uses, draws it inside `PLACES_BAND` at some camera longitude of the turn. The mean latitude used before let the dots dominate. Ten dots near 48°N and one on Rapa Nui (-27.1°) gave a mean of 41.2, which leaves the Rapa Nui dot 68.3° away, beyond the 65.8° horizon for the whole turn. `take_events` would refuse that only after a take of many minutes. When no latitude admits every place, `scene_input` refuses the spec before any side effect: split the distribution. The page's own pixels still decide in `take_events`. The dots come from our database by site id (owner decision 15): plan C's `captures.py` resolves the script's `site_ids` from the repo-root `public/data/sites/` export and hands them to `record_globe` as unlabelled places `{id: <site id>, lat, lng}`, so this module needs no change for them; a test pins that a dot keeps its site id as the event's `target` and carries no label. A fly-to with a `place` tracks its target the same way and adds the target's `place` event at the arrival; `arrive` itself carries only the frame centre. Root cause of the recorder failure the first studio capture hit (`EBML header parsing failed`, 2026-09-26): the recorder's MediaRecorder stream drops frames when its VP8 encoder falls behind (22, 66 and 0 of 300 frames in three takes); the 0-frame take is an empty WebM. The studio scenes therefore grab every frame themselves and this module encodes the numbered JPEGs (Task 25). A Mapbox fly-in waits for its tiles on every frame (5 s took 17 min), hence the 90-minute limit. A failed encode is a `CaptureError` naming ffmpeg and its stderr. The recorder is faked in the tests.

- [ ] **Step 1: Write the failing test**

**`tests/pipeline/studio/capture/test_capture_globe.py`** (complete file):

```python
"""Globe and Mapbox takes (pipeline/studio/capture/globe.py); the recorder itself is faked."""

import json
import subprocess
from contextlib import nullcontext
from pathlib import Path

import pytest

from pipeline.studio.capture import globe
from pipeline.studio.capture.gpu import nvenc_problem
from pipeline.studio.capture.manifest import CREDIT_MAPBOX_STREETS, CaptureError

NVIDIA = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)"
NVENC_PROBLEM = nvenc_problem()
needs_nvenc = pytest.mark.skipif(NVENC_PROBLEM is not None, reason=str(NVENC_PROBLEM))

FLYTO = {
    "id": "g1",
    "kind": "globe",
    "scene": "flyto",
    "lat": 34.0067,
    "lng": 36.2033,
    "distance": 1.35,
    "empire": "roman",
    "rotate_s": 1.5,
    "zoom_s": 2.0,
    "duration_s": 5,
    "place": {"id": "p1", "label": "Baalbek"},
}
PLACES = {
    "id": "g2",
    "kind": "globe",
    "scene": "places",
    "places": [
        {"id": "p2", "label": "Giza", "lat": 29.98, "lng": 31.13},
        {"id": "p3", "label": "Athens", "lat": 37.97, "lng": 23.73},
        {"id": "p1", "label": "Baalbek", "lat": 34.0, "lng": 36.2},
    ],
    "lead_s": 0.8,
    "interval_s": 0.6,
    "duration_s": 6,
}
DISTRIBUTION = {
    "id": "g3",
    "kind": "globe",
    "scene": "distribution",
    "duration_s": 12,
    "places": [
        {"id": "p1", "label": "Baalbek", "lat": 34.0, "lng": 36.2},
        {"id": "d1", "lat": -13.16, "lng": -72.55},
    ],
}
FLYIN = {
    "id": "m1",
    "kind": "globe",
    "scene": "mapbox_flyin",
    "name": "Baalbek",
    "lat": 34.0067,
    "lng": 36.2033,
    "country": "Lebanon",
    "orbit_zoom": 15.5,
    "duration_s": 8,
}
ORBIT = {
    "id": "m2",
    "kind": "globe",
    "scene": "mapbox_orbit",
    "name": "Baalbek",
    "lat": 34.0067,
    "lng": 36.2033,
    "zoom": 16.5,
    "pitch": 60,
    "bearing_from": 20,
    "bearing_to": 110,
    "duration_s": 6,
}
WORK = Path("C:/ep/captures/g1.rec")


def tracks(pixels: dict, frames: int) -> dict:
    """points.json of a fixed pose: each place at one pixel (or hidden) in every frame."""
    return {pid: [None if px is None else list(px)] * frames for pid, px in pixels.items()}


def test_every_scene_has_a_recorder_scene_and_credits():
    assert globe.RECORDER_SCENES == {
        "flyto": "studio-globe-flyto",
        "places": "studio-globe-places",
        "distribution": "studio-globe-places",
        "mapbox_flyin": "studio-mapbox-flyin",
        "mapbox_orbit": "studio-mapbox-orbit",
    }
    assert globe.CREDITS["flyto"] == [] and globe.CREDITS["distribution"] == []
    assert globe.CREDITS["mapbox_flyin"] == [CREDIT_MAPBOX_STREETS]


def test_flyto_input_and_events():
    inp = globe.scene_input(FLYTO, WORK)
    assert inp == {
        "scene": "flyto",
        "duration_s": 5.0,
        "frames_dir": "C:/ep/captures/g1.rec/frames",
        "renderer_path": "C:/ep/captures/g1.rec/renderer.json",
        "lat": 34.0067,
        "lng": 36.2033,
        "distance": 1.35,
        "empire": "roman",
        "rotate_s": 1.5,
        "zoom_s": 2.0,
        "places": [{"id": "p1", "lat": 34.0067, "lng": 36.2033}],
        "points_path": "C:/ep/captures/g1.rec/points.json",
    }
    frames = globe.expected_frames(5)
    # the target drifts in from the corner during the fly-to and sits at the centre on arrival
    track = [[1500.0, 900.0]] * 150 + [[960.0, 540.0]] * (frames - 150)
    events = globe.take_events(FLYTO, inp, {"p1": track})
    assert events[:3] == [
        {"t": 0.0, "name": "rotate"},
        {"t": 1.5, "name": "zoom"},
        {"t": 3.5, "name": "arrive", "x": 960.0, "y": 540.0},
    ]
    place = events[3]
    assert {k: v for k, v in place.items() if k != "track"} == {
        "t": 3.5,
        "name": "place",
        "x": 960.0,
        "y": 540.0,
        "target": "p1",
        "label": "Baalbek",
    }
    assert len(place["track"]) == frames - 210
    plain = {k: v for k, v in FLYTO.items() if k != "place"}
    plain_inp = globe.scene_input(plain, WORK)
    assert "points_path" not in plain_inp
    assert [e["name"] for e in globe.take_events(plain, plain_inp, None)] == [
        "rotate",
        "zoom",
        "arrive",
    ]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"distance": 1.05}, "distance=1.05 outside"),
        ({"duration_s": 3.5}, r"rotate_s \+ zoom_s \+ 0.5 s hold"),
        ({"duration_s": 31}, "duration_s=31.0 outside"),
        ({"lat": 95}, "not a coordinate"),
        ({"lat": "34"}, "g1: lat must be a number"),
        ({"empire": ""}, "empire must be"),
        ({"empire": "atlantis"}, "empire must be null or an empire id"),
        ({"emprie": "roman"}, r"unknown keys \['emprie'\] for scene flyto"),
        ({"place": {"id": "p1"}}, "place must be"),
        ({"scene": "street-view"}, "scene must be one of"),
    ],
)
def test_flyto_rejects_bad_specs(changes, message):
    with pytest.raises(CaptureError, match=message):
        globe.scene_input({**FLYTO, **changes}, WORK)


def test_places_pose_and_events_use_the_pixels_the_page_reported():
    inp = globe.scene_input(PLACES, WORK)
    assert (inp["scene"], inp["sweep_lng_deg"]) == ("places", 0.0)
    assert inp["places"] == [
        {"id": "p2", "lat": 29.98, "lng": 31.13},
        {"id": "p3", "lat": 37.97, "lng": 23.73},
        {"id": "p1", "lat": 34.0, "lng": 36.2},
    ]
    assert inp["points_path"] == "C:/ep/captures/g1.rec/points.json"
    assert 1.2 <= inp["distance"] <= 2.44
    frames = globe.expected_frames(6)
    points = tracks({"p2": (900.0, 700.0), "p3": (500.0, 400.0), "p1": (1100.0, 520.0)}, frames)
    events = globe.take_events(PLACES, inp, points)
    assert [(e["target"], e["label"], e["t"], e["x"], e["y"], len(e["track"])) for e in events] == [
        ("p2", "Giza", 0.8, 900.0, 700.0, frames - 48),
        ("p3", "Athens", 1.4, 500.0, 400.0, frames - 84),
        ("p1", "Baalbek", 2.0, 1100.0, 520.0, frames - 120),
    ]


def test_places_hidden_outside_the_band_or_too_late_are_rejected():
    inp = globe.scene_input(PLACES, WORK)
    frames = globe.expected_frames(6)
    with pytest.raises(CaptureError, match="p3 is not visible in the take"):
        globe.take_events(PLACES, inp, tracks({"p2": (900, 700), "p3": None, "p1": (1, 1)}, frames))
    # the first real places take drew Giza at y 946: its label would sit under the controls
    low = tracks({"p2": (1232.2, 946.5), "p3": (823, 426), "p1": (1100, 520)}, frames)
    with pytest.raises(CaptureError, match=r"draws place p2 at \(0\.64, 0\.88\) of the frame"):
        globe.take_events(PLACES, inp, low)
    short = tracks({"p2": (900, 700), "p3": (500, 400), "p1": (1100, 520)}, 10)
    with pytest.raises(
        CaptureError, match="points.json holds 10 points for place p2, the take has 360"
    ):
        globe.take_events(PLACES, inp, short)
    # checked before the take: lead_s + 2 * interval_s = 10.8 s > 6 s
    with pytest.raises(CaptureError, match="p1 would light up after the take ends"):
        globe.scene_input({**PLACES, "interval_s": 5.0}, WORK)
    with pytest.raises(CaptureError, match=r"interval_s=0.05 outside 0.1..5.0"):
        globe.scene_input({**PLACES, "interval_s": 0.05}, WORK)


def test_a_sweep_moves_the_camera_and_each_pin_follows_its_track():
    spec = {
        **PLACES,
        "places": PLACES["places"][:1],
        "lead_s": 0.5,
        "sweep_lng_deg": 120,
        "cam_lat": 30,
        "cam_lng_from": 0,
        "distance": 2.2,
    }
    inp = globe.scene_input(spec, WORK)
    assert (inp["cam_lat"], inp["cam_lng"], inp["distance"], inp["sweep_lng_deg"]) == (
        30.0,
        0.0,
        2.2,
        120.0,
    )
    frames = globe.expected_frames(6)
    # behind the globe until frame 40, left of the label band until frame 60, then moving right
    track = [None] * 40 + [[100.0, 500.0]] * 20 + [[300.0 + f, 500.0] for f in range(frames - 60)]
    (place,) = globe.take_events(spec, inp, {"p2": track})
    assert (place["t"], place["x"], place["track"][0]) == (1.0, 300.0, [300.0, 500.0])
    assert len(place["track"]) == frames - 60 and place["track"][-1] == [599.0, 500.0]
    with pytest.raises(CaptureError, match="belong to a sweep"):
        globe.scene_input({**PLACES, "cam_lat": 30}, WORK)


def test_a_world_distribution_turns_the_whole_globe_once():
    inp = globe.scene_input(DISTRIBUTION, WORK)
    assert (inp["scene"], inp["sweep_lng_deg"], inp["distance"]) == ("places", 360.0, 2.44)
    assert inp["places"] == [
        {"id": "p1", "lat": 34.0, "lng": 36.2},
        {"id": "d1", "lat": -13.16, "lng": -72.55},
    ]
    # the camera starts opposite the places' mean longitude, at the midpoint of their
    # lowest and highest latitude, where one turn shows both
    assert inp["cam_lat"] == pytest.approx(10.42)
    assert inp["cam_lng"] == pytest.approx(161.82, abs=0.01)
    frames = globe.expected_frames(12)
    near = [None] * 100 + [[960.0, 500.0]] * (frames - 100)
    far = [None] * 500 + [[1500.0, 1000.0]] * (frames - 500)
    pin, dot = globe.take_events(DISTRIBUTION, inp, {"d1": far, "p1": near})
    assert (pin["target"], pin["label"], pin["t"]) == ("p1", "Baalbek", round(100 / 60, 3))
    # an unlabelled place is a dot: no label, and the label band does not apply to it
    assert "label" not in dot and (dot["t"], dot["x"], dot["y"]) == (
        round(500 / 60, 3),
        1500.0,
        1000.0,
    )
    with pytest.raises(CaptureError, match="places must list 1-500 places"):
        globe.scene_input({**DISTRIBUTION, "places": []}, WORK)
    with pytest.raises(CaptureError, match="place ids must be unique"):
        globe.scene_input({**DISTRIBUTION, "places": DISTRIBUTION["places"][:1] * 2}, WORK)


def test_a_distribution_dot_is_a_site_id_without_a_label():
    # owner decision 15: plan C resolves a distribution's site_ids from the site export
    # into unlabelled places {id, lat, lng}; each becomes a dot, its site id the target
    site = "be81c1a6-5d0c-4f7e-9a51-3c2d7e8f9a10"
    spec = {
        **DISTRIBUTION,
        "places": [DISTRIBUTION["places"][0], {"id": site, "lat": 37.2231, "lng": 38.9224}],
    }
    inp = globe.scene_input(spec, WORK)
    assert inp["places"][1] == {"id": site, "lat": 37.2231, "lng": 38.9224}
    frames = globe.expected_frames(12)
    seen = [None] * 200 + [[700.0, 400.0]] * (frames - 200)
    pin, dot = globe.take_events(spec, inp, {site: seen, "p1": [[960.0, 500.0]] * frames})
    assert pin["target"] == "p1" and pin["label"] == "Baalbek"
    assert (dot["name"], dot["target"], dot["t"], dot["x"], dot["y"]) == (
        "place",
        site,
        round(200 / 60, 3),
        700.0,
        400.0,
    )
    assert "label" not in dot and len(dot["track"]) == frames - 200


def test_the_distribution_camera_shows_the_outlying_places_too():
    # ten dots near 48 N and one on Rapa Nui: their mean latitude (41.2) would keep the
    # Rapa Nui dot 68.3 degrees away, beyond the horizon (65.8) for the whole turn
    north = [{"id": f"n{i}", "lat": 48.0, "lng": -10.0 + 5 * i} for i in range(10)]
    rapa_nui = {"id": "s1", "lat": -27.1, "lng": -109.35}
    inp = globe.scene_input({**DISTRIBUTION, "places": [*north, rapa_nui]}, WORK)
    assert inp["cam_lat"] == pytest.approx(10.45)
    for place in inp["places"]:
        assert abs(place["lat"] - inp["cam_lat"]) <= globe.DISTRIBUTION_DOT_REACH_DEG
    # a labelled place far south of the dots: the midpoint (2.5) would draw its pin below
    # the label band, so the camera moves south to the nearest latitude that shows it there
    dots = [{**n, "lat": 45.0} for n in north]
    pin = {"id": "p9", "label": "Far south", "lat": -40.0, "lng": -72.55}
    inp = globe.scene_input({**DISTRIBUTION, "places": [*dots, pin]}, WORK)
    assert inp["cam_lat"] == -14.0


def test_a_distribution_one_turn_cannot_show_is_refused_before_the_take(tmp_path):
    spec = {
        **DISTRIBUTION,
        "places": [
            {"id": "n1", "lat": 70.0, "lng": 20.0},
            {"id": "s1", "lat": -66.0, "lng": 140.0},
        ],
    }
    with pytest.raises(
        CaptureError,
        match=r"g3: places \['n1', 's1'\] cannot face the camera in one turn of the globe; "
        "split the distribution",
    ):
        globe.record_globe(tmp_path, spec)
    assert not (tmp_path / "captures").exists()


def test_mapbox_inputs():
    flyin = globe.scene_input(FLYIN, WORK)
    assert (flyin["name"], flyin["country"], flyin["orbit_zoom"]) == ("Baalbek", "Lebanon", 15.5)
    assert [e["name"] for e in globe.take_events(FLYIN, flyin, None)] == ["space", "zoom", "orbit"]
    orbit = globe.scene_input({**ORBIT, "country": None}, WORK)
    assert "country" not in orbit and orbit["bearing_to"] == 110.0
    with pytest.raises(CaptureError, match="at least 4.6 s"):
        globe.scene_input({**FLYIN, "duration_s": 4}, WORK)
    with pytest.raises(CaptureError, match=r"unknown keys \['pitch'\] for scene mapbox_flyin"):
        globe.scene_input({**FLYIN, "pitch": 60}, WORK)


def test_recorder_command_records_landscape_at_60fps():
    cmd = globe.recorder_command(
        "npm", "studio-globe-flyto", Path("C:/ep/in.json"), Path("C:/ep/rec")
    )
    assert cmd == [
        "npm",
        "run",
        "video:record",
        "--",
        "studio-globe-flyto",
        "--fps",
        "60",
        "--input",
        "C:/ep/in.json",
        "--out",
        "C:/ep/rec",
    ]
    assert "--portrait" not in cmd


def test_frames_are_counted_like_the_recorder_scenes():
    assert globe.expected_frames(5) == 300
    assert globe.expected_frames(3.51) == 211
    # JS Math.round rounds 304.5 up; Python's round() would give 304
    assert globe.expected_frames(5.075) == 305


def test_record_globe_validates_before_starting_anything(tmp_path):
    with pytest.raises(CaptureError, match="takes kind 'globe'"):
        globe.record_globe(tmp_path, {**FLYTO, "kind": "globe-flyto"})
    with pytest.raises(CaptureError, match="distance"):
        globe.record_globe(tmp_path, {**FLYTO, "distance": 3})
    assert not (tmp_path / "captures").exists()


class FakeRecorder:
    """Stands in for `npm run video:record`: writes what the scene would (frames, renderer, points)."""

    frames = 300
    returncode = 0
    renderer = NVIDIA

    def __init__(self, cmd, log):
        from PIL import Image

        assert cmd[:5] == ["npm", "run", "video:record", "--", "studio-globe-flyto"]
        inp = json.loads(Path(cmd[cmd.index("--input") + 1]).read_text(encoding="utf-8"))
        Path(inp["renderer_path"]).write_text(
            json.dumps({"renderer": self.renderer}), encoding="utf-8"
        )
        frames = Path(inp["frames_dir"])
        frames.mkdir(parents=True)
        for i in range(self.frames):
            Image.new("RGB", (1920, 1080), (i % 255, 40, 80)).save(frames / f"f{i:06d}.jpg")
        points = {p["id"]: [[960.0, 540.0]] * self.frames for p in inp["places"]}
        Path(inp["points_path"]).write_text(json.dumps(points), encoding="utf-8")

    def wait(self, timeout):
        return self.returncode


@pytest.fixture
def workstation(monkeypatch):
    """The workstation parts of a take the tests replace: npm on PATH and the awake display."""
    monkeypatch.setattr(globe, "require_tool", lambda name: "npm")
    monkeypatch.setattr(globe, "display_awake", nullcontext)


@needs_nvenc
def test_record_globe_encodes_the_exact_frames_and_cleans_up(tmp_path, monkeypatch, workstation):
    monkeypatch.setattr(globe, "start_recorder", FakeRecorder)
    manifest = globe.record_globe(tmp_path, FLYTO)
    assert manifest["path"] == "captures/g1.mp4" and (tmp_path / manifest["path"]).is_file()
    assert (manifest["fps"], manifest["duration_s"], manifest["width"], manifest["height"]) == (
        60,
        5.0,
        1920,
        1080,
    )
    assert manifest["events"][0] == {"t": 0.0, "name": "gpu", "label": NVIDIA}
    place = manifest["events"][-1]
    assert manifest["credits"] == [] and place["label"] == "Baalbek" and len(place["track"]) == 90
    assert not (tmp_path / "captures" / "g1.rec").exists()


def test_a_take_drawn_on_another_gpu_fails(tmp_path, monkeypatch, workstation):
    class OnAmd(FakeRecorder):
        frames = 2
        renderer = (
            "ANGLE (AMD, AMD Radeon(TM) Graphics (0x00001681) Direct3D11 vs_5_0 ps_5_0, D3D11)"
        )

    monkeypatch.setattr(globe, "start_recorder", OnAmd)
    with pytest.raises(CaptureError, match="g1: recorder: Chrome draws on .*AMD.*not the NVIDIA"):
        globe.record_globe(tmp_path, FLYTO)


def test_a_take_with_missing_frames_fails_before_the_encode(tmp_path, monkeypatch, workstation):
    class Short(FakeRecorder):
        frames = 250

    monkeypatch.setattr(globe, "start_recorder", Short)
    with pytest.raises(CaptureError, match="the take has 250 frames, expected 300"):
        globe.record_globe(tmp_path, FLYTO)


def test_an_encoder_failure_names_the_tool_and_its_stderr(tmp_path, monkeypatch, workstation):
    def broken(frames_dir, fps, out):
        raise subprocess.CalledProcessError(
            1,
            ["C:/ffmpeg/bin/ffmpeg.exe", "-i", "f%06d.jpg"],
            stderr="No NVENC capable devices found\n",
        )

    monkeypatch.setattr(globe, "start_recorder", FakeRecorder)
    monkeypatch.setattr(globe, "sequence_to_mp4", broken)
    with pytest.raises(
        CaptureError, match=r"g1: ffmpeg.exe failed \(exit 1\): No NVENC capable devices found"
    ) as err:
        globe.record_globe(tmp_path, FLYTO)
    assert isinstance(err.value.__cause__, subprocess.CalledProcessError)


def test_a_failed_recorder_points_at_its_log(tmp_path, monkeypatch, workstation):
    class Failed(FakeRecorder):
        frames = 1
        returncode = 1

    monkeypatch.setattr(globe, "start_recorder", Failed)
    with pytest.raises(CaptureError, match=r"recorder failed \(exit 1\); see .*recorder.log"):
        globe.record_globe(tmp_path, FLYTO)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_globe.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL with `ImportError: cannot import name 'globe' from 'pipeline.studio.capture'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/globe.py`** (complete file):

```python
"""Globe and Mapbox takes through the Puppeteer recorder (spec 2026-09-26 section 4.5).

Wraps ``npm run video:record`` (ancient-nerds-map/video/record.ts) with the landscape
studio scenes of ancient-nerds-map/video/scenes/studio-globe.ts and studio-mapbox.ts.
The scene input goes to ``captures/<id>.rec/input.json`` (``--input``; record.ts exposes
it as STUDIO_SCENE_INPUT). The scenes grab every frame exactly
(video/scenes/studio-frames.ts) into ``captures/<id>.rec/frames``; this module checks
the count, encodes the sequence (encode.sequence_to_mp4) and builds the manifest. Every
scene writes the page's WebGL renderer to renderer.json, which must name the NVIDIA
(spec 4.11; the recorder launches Chrome with the NVIDIA flags) and becomes the "gpu"
event. The places scene, and a fly-to with a place, also write where the page drew each
place in every grabbed frame (points.json: {place id: [[x, y] | null, ...]}, one entry
per frame, from window.__DEMO.screenPoint): the owner's rule for globe markers is to
project them per frame from their coordinates, so the renderer's pins follow the globe
when the camera moves. The display is held awake for the take.

Specs (kind "globe"; duration_s is the length of the take, at most 30 s)::

    {"id": "g1", "kind": "globe", "scene": "flyto", "lat": 34.0067, "lng": 36.2033,
     "distance": 1.35, "empire": "roman" | null, "rotate_s": 1.5, "zoom_s": 2.0,
     "duration_s": 5, "place": {"id": "p1", "label": "Baalbek"}}  (empire, place optional)
    {"id": "g2", "kind": "globe", "scene": "places",
     "places": [{"id": "p1", "label": "Baalbek", "lat": .., "lng": ..}, ...],
     "lead_s": 0.8, "interval_s": 0.6, "duration_s": 6}           (a fixed pose framing all)
    {... "scene": "places", ..., "sweep_lng_deg": 120, "cam_lat": 30,
     "cam_lng_from": 0, "distance": 2.2}                            (the camera sweeps east)
    {"id": "g3", "kind": "globe", "scene": "distribution", "duration_s": 20,
     "places": [{"id": "p1", "lat": .., "lng": .., "label": "Baalbek"},
                {"id": "<site id>", "lat": .., "lng": ..}, ...]}     (1-500, label optional)
    {"id": "m1", "kind": "globe", "scene": "mapbox_flyin", "name": "Baalbek", "lat": ..,
     "lng": .., "country": "Lebanon", "orbit_zoom": 15.5, "duration_s": 8}
    {"id": "m2", "kind": "globe", "scene": "mapbox_orbit", "name": "Baalbek", "lat": ..,
     "lng": .., "zoom": 16.5, "pitch": 60, "bearing_from": 20, "bearing_to": 110,
     "duration_s": 6}

Events: flyto "rotate", "zoom", "arrive" (the frame centre) and, with a place, the
place's "place" event; places one "place" event per place at the first frame from
lead_s + i * interval_s on where the page draws it inside PLACES_BAND; a distribution
(one full turn of the globe, the whole globe in frame, at a camera latitude from which
one turn can show every place: distribution_pose) one "place" event per place at the
first frame the place faces the camera, where unlabelled places are dots the band does
not apply to; a "place" event carries x/y of its frame and ``track``, the pixel in
every frame from there to the end of the take (null while hidden or, for a labelled
place, outside PLACES_BAND). Place ids are case-file place ids and a label is the
case-file place's name (plan C binds both to the verified case file before a take): the
renderer's GlobeShot pins and their show cues use them. The unlabelled places of a
distribution are its dots: plan C resolves the script's `site_ids` from the repo-root
public/data/sites export into {id: <site id>, lat, lng} (owner decision 15), so their ids
are site ids and never cue targets. A Mapbox take's optional "country" is the country the
take highlights: plan C binds it to the site export's country of its place, and the
recorder refuses a name the site's country table does not know (studio-mapbox.ts
checkCountry), so the recorder exits 1 and the take is a CaptureError.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.historical_boundaries.empire_metadata import EMPIRE_METADATA
from pipeline.studio.capture.encode import sequence_length, sequence_to_mp4
from pipeline.studio.capture.gpu import gpu_event, require_nvidia
from pipeline.studio.capture.manifest import (
    CREDIT_MAPBOX_STREETS,
    CaptureError,
    as_number,
    build_manifest,
    event,
    media_path,
    require_kind,
    tool_failure,
)
from pipeline.studio.capture.projection import (
    GLOBE_MAX_DISTANCE,
    GLOBE_MIN_DISTANCE,
    PLACES_BAND,
    fit_globe_distance,
    globe_to_pixel,
)
from pipeline.studio.capture.vite import (
    FRONTEND_DIR,
    PRODUCTION_URL,
    display_awake,
    kill_tree,
    require_mapbox_token,
    require_tool,
)
from pipeline.utils.geo import is_valid_coordinates

FPS = 60
WIDTH, HEIGHT = 1920, 1080
MAX_TAKE_S = 30.0
# A Mapbox fly-in waits for its tiles on every frame: 5 s took 17 min (2026-09-26).
RECORD_TIMEOUT_S = 90 * 60
RECORDER_SCENES = {
    "flyto": "studio-globe-flyto",
    "places": "studio-globe-places",
    "distribution": "studio-globe-places",
    "mapbox_flyin": "studio-mapbox-flyin",
    "mapbox_orbit": "studio-mapbox-orbit",
}
_BASE_KEYS = {"id", "kind", "scene", "duration_s"}
SPEC_KEYS = {
    "flyto": frozenset(
        _BASE_KEYS | {"lat", "lng", "distance", "empire", "rotate_s", "zoom_s", "place"}
    ),
    "places": frozenset(
        _BASE_KEYS
        | {"places", "lead_s", "interval_s", "sweep_lng_deg", "cam_lat", "cam_lng_from", "distance"}
    ),
    "distribution": frozenset(_BASE_KEYS | {"places"}),
    "mapbox_flyin": frozenset(_BASE_KEYS | {"name", "lat", "lng", "country", "orbit_zoom"}),
    "mapbox_orbit": frozenset(
        _BASE_KEYS
        | {"name", "lat", "lng", "country", "zoom", "pitch", "bearing_from", "bearing_to"}
    ),
}
SWEEP_KEYS = frozenset({"cam_lat", "cam_lng_from", "distance"})
MAX_PLACES = 12
MAX_DISTRIBUTION_PLACES = 500
# A world distribution: the whole globe in frame, one full turn over the take.
DISTRIBUTION_DISTANCE = GLOBE_MAX_DISTANCE
DISTRIBUTION_SWEEP_DEG = 360.0
DISTRIBUTION_MAX_LAT = 45
# A dot faces the camera of the turn when it lies within the horizon, acos(1 / distance)
# from the point under the camera (65.8 degrees at 2.44), less this margin at the limb.
DISTRIBUTION_HORIZON_MARGIN_DEG = 5.0
DISTRIBUTION_DOT_REACH_DEG = (
    math.degrees(math.acos(1 / DISTRIBUTION_DISTANCE)) - DISTRIBUTION_HORIZON_MARGIN_DEG
)
# Camera longitudes of one full turn relative to a place, in whole degrees, nearest first.
TURN_DELTAS_DEG = sorted(range(-180, 180), key=abs)
# Mirrors of ancient-nerds-map/video/scenes/studio-mapbox.ts (the path timing the events describe).
FLYIN_ROTATE_S = 1.2
FLYIN_ZOOM_S = 2.4
# Our vector globe carries no third-party map data; the Mapbox takes use satellite-streets.
CREDITS = {
    "flyto": [],
    "places": [],
    "distribution": [],
    "mapbox_flyin": [CREDIT_MAPBOX_STREETS],
    "mapbox_orbit": [CREDIT_MAPBOX_STREETS],
}


def _num(spec: dict[str, Any], key: str, lo: float, hi: float) -> float:
    if key not in spec:
        raise CaptureError(f"{spec.get('id')}: missing {key!r}")
    value = as_number(spec[key], f"{spec.get('id')}: {key}")
    if not lo <= value <= hi:
        raise CaptureError(f"{spec.get('id')}: {key}={value} outside {lo}..{hi}")
    return value


def _coords(spec: dict[str, Any], where: str) -> tuple[float, float]:
    for key in ("lat", "lng"):
        if key not in spec:
            raise CaptureError(f"{where}: missing {key!r}")
    lat, lng = as_number(spec["lat"], f"{where}: lat"), as_number(spec["lng"], f"{where}: lng")
    if not is_valid_coordinates(lat, lng):
        raise CaptureError(f"{where}: ({lat}, {lng}) is not a coordinate")
    return lat, lng


def _label(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError(f"{where}: needs a non-empty label")
    return value


def _places(spec: dict[str, Any], most: int, label_required: bool) -> list[dict[str, Any]]:
    """The spec's places, each {id, lat, lng} plus its label (required, or optional)."""
    cid = spec.get("id")
    places = spec.get("places")
    if not isinstance(places, list) or not 1 <= len(places) <= most:
        raise CaptureError(f"{cid}: places must list 1-{most} places")
    out = []
    for i, place in enumerate(places):
        keys = set(place) if isinstance(place, dict) else set()
        allowed = {"id", "label", "lat", "lng"}
        needed = allowed if label_required else allowed - {"label"}
        if not isinstance(place, dict) or not needed <= keys <= allowed:
            shape = "{id, label, lat, lng}" if label_required else "{id, lat, lng, label?}"
            raise CaptureError(f"{cid}: places[{i}] must be {shape}")
        if not isinstance(place["id"], str) or not place["id"]:
            raise CaptureError(f"{cid}: places[{i}] needs a place id")
        lat, lng = _coords(place, f"{cid}: place {place['id']}")
        clean = {"id": place["id"], "lat": lat, "lng": lng}
        if "label" in place:
            clean["label"] = _label(place["label"], f"{cid}: places[{i}]")
        out.append(clean)
    if len({p["id"] for p in out}) != len(out):
        raise CaptureError(f"{cid}: place ids must be unique")
    return out


def _faces_camera(place: dict[str, Any], cam_lat: float) -> bool:
    """Whether one turn of the distribution camera at `cam_lat` can show the place.

    A dot must lie within the horizon less a margin; a labelled place must be drawn inside
    PLACES_BAND at some camera longitude of the turn, by projection.py's globe camera (the
    model fit_globe_distance uses; the page's own pixels decide later, in take_events).
    """
    if "label" not in place:
        return abs(place["lat"] - cam_lat) <= DISTRIBUTION_DOT_REACH_DEG
    for delta in TURN_DELTAS_DEG:
        px = globe_to_pixel(
            place["lat"],
            place["lng"],
            cam_lat=cam_lat,
            cam_lng=place["lng"] + delta,
            distance=DISTRIBUTION_DISTANCE,
            width=WIDTH,
            height=HEIGHT,
        )
        if px is not None and _in_band(px):
            return True
    return False


def distribution_pose(cid: str, places: list[dict[str, Any]]) -> tuple[float, float]:
    """(cam_lat, cam_lng_from) of a world distribution.

    The camera starts opposite the places' mean longitude, so the densest region turns
    into view in the middle of the take. Its latitude is the midpoint of the places'
    lowest and highest latitude, or else the whole degree nearest it, within +-45, at
    which one turn can show every place (_faces_camera); the mean latitude would follow
    the dots and lose an outlying place. Raises before any side effect when no latitude
    shows them all.
    """
    lats = [p["lat"] for p in places]
    mid = max(-DISTRIBUTION_MAX_LAT, min(DISTRIBUTION_MAX_LAT, (min(lats) + max(lats)) / 2))
    whole = range(-DISTRIBUTION_MAX_LAT, DISTRIBUTION_MAX_LAT + 1)
    candidates = sorted([mid, *(float(c) for c in whole)], key=lambda c: abs(c - mid))
    cam_lat = next((c for c in candidates if all(_faces_camera(p, c) for p in places)), None)
    if cam_lat is None:
        ids = [p["id"] for p in places if not _faces_camera(p, mid)]
        raise CaptureError(
            f"{cid}: places {ids} cannot face the camera in one turn of the globe; "
            "split the distribution"
        )
    x = sum(math.cos(math.radians(p["lng"])) for p in places)
    y = sum(math.sin(math.radians(p["lng"])) for p in places)
    start = math.degrees(math.atan2(y, x)) - 180.0
    return cam_lat, start + 360.0 if start < -180.0 else start


def scene_input(spec: dict[str, Any], work: Path) -> dict[str, Any]:
    """Validate a globe spec and build the recorder scene input (studio-*.ts) for `work`."""
    cid = spec.get("id")
    scene = spec.get("scene")
    if scene not in RECORDER_SCENES:
        raise CaptureError(f"{cid}: scene must be one of {sorted(RECORDER_SCENES)}, got {scene!r}")
    unknown = set(spec) - SPEC_KEYS[scene]
    if unknown:
        raise CaptureError(f"{cid}: unknown keys {sorted(unknown)} for scene {scene}")
    duration = _num(spec, "duration_s", 1.0, MAX_TAKE_S)
    base: dict[str, Any] = {
        "scene": "places" if scene == "distribution" else scene,
        "duration_s": duration,
        "frames_dir": (work / "frames").as_posix(),
        "renderer_path": (work / "renderer.json").as_posix(),
    }
    points_path = (work / "points.json").as_posix()
    if scene == "flyto":
        lat, lng = _coords(spec, str(cid))
        rotate_s = _num(spec, "rotate_s", 0.5, 5.0)
        zoom_s = _num(spec, "zoom_s", 0.5, 5.0)
        if duration < rotate_s + zoom_s + 0.5:
            raise CaptureError(f"{cid}: duration_s {duration} < rotate_s + zoom_s + 0.5 s hold")
        empire = spec.get("empire")
        if empire is not None and empire not in EMPIRE_METADATA:
            raise CaptureError(
                f"{cid}: empire must be null or an empire id of "
                f"pipeline/historical_boundaries/empire_metadata.py, got {empire!r}"
            )
        place = spec.get("place")
        if place is not None and (not isinstance(place, dict) or set(place) != {"id", "label"}):
            raise CaptureError(f"{cid}: place must be {{'id': <place id>, 'label': ...}}")
        out = {
            **base,
            "lat": lat,
            "lng": lng,
            "distance": _num(spec, "distance", GLOBE_MIN_DISTANCE, GLOBE_MAX_DISTANCE),
            "empire": empire,
            "rotate_s": rotate_s,
            "zoom_s": zoom_s,
        }
        if place is not None:
            _label(place["label"], f"{cid}: place")
            out["places"] = [{"id": place["id"], "lat": lat, "lng": lng}]
            out["points_path"] = points_path
        return out
    if scene == "places":
        places = _places(spec, MAX_PLACES, label_required=True)
        lead = _num(spec, "lead_s", 0.0, duration)
        interval = _num(spec, "interval_s", 0.1, 5.0)
        if lead + (len(places) - 1) * interval > duration:
            raise CaptureError(
                f"{cid}: place {places[-1]['id']} would light up after the take ends "
                f"(lead_s + {len(places) - 1} * interval_s > duration_s)"
            )
        sweep = _num(spec, "sweep_lng_deg", -360.0, 360.0) if "sweep_lng_deg" in spec else 0.0
        if sweep == 0:
            if SWEEP_KEYS & set(spec):
                raise CaptureError(
                    f"{cid}: {sorted(SWEEP_KEYS & set(spec))} belong to a sweep "
                    "(sweep_lng_deg != 0); a fixed pose is fitted to the places"
                )
            try:
                cam_lat, cam_lng, distance = fit_globe_distance(
                    [(p["lat"], p["lng"]) for p in places], width=WIDTH, height=HEIGHT
                )
            except ValueError as err:
                raise CaptureError(f"{cid}: {err}") from err
        else:
            cam_lat = _num(spec, "cam_lat", -60.0, 60.0)
            cam_lng = _num(spec, "cam_lng_from", -180.0, 180.0)
            distance = _num(spec, "distance", GLOBE_MIN_DISTANCE, GLOBE_MAX_DISTANCE)
        return {
            **base,
            "cam_lat": cam_lat,
            "cam_lng": cam_lng,
            "distance": distance,
            "sweep_lng_deg": sweep,
            "places": [{"id": p["id"], "lat": p["lat"], "lng": p["lng"]} for p in places],
            "points_path": points_path,
        }
    if scene == "distribution":
        places = _places(spec, MAX_DISTRIBUTION_PLACES, label_required=False)
        cam_lat, cam_lng = distribution_pose(str(cid), places)
        return {
            **base,
            "cam_lat": cam_lat,
            "cam_lng": cam_lng,
            "distance": DISTRIBUTION_DISTANCE,
            "sweep_lng_deg": DISTRIBUTION_SWEEP_DEG,
            "places": [{"id": p["id"], "lat": p["lat"], "lng": p["lng"]} for p in places],
            "points_path": points_path,
        }
    lat, lng = _coords(spec, str(cid))
    out = {**base, "name": _label(spec.get("name"), str(cid)), "lat": lat, "lng": lng}
    if spec.get("country") is not None:
        out["country"] = str(spec["country"])
    if scene == "mapbox_flyin":
        if duration < FLYIN_ROTATE_S + FLYIN_ZOOM_S + 1:
            raise CaptureError(
                f"{cid}: a fly-in needs at least {FLYIN_ROTATE_S + FLYIN_ZOOM_S + 1} s"
            )
        out["orbit_zoom"] = _num(spec, "orbit_zoom", 10.0, 18.0)
    else:
        out["zoom"] = _num(spec, "zoom", 10.0, 18.5)
        out["pitch"] = _num(spec, "pitch", 0.0, 80.0)
        out["bearing_from"] = _num(spec, "bearing_from", -360.0, 360.0)
        out["bearing_to"] = _num(spec, "bearing_to", -360.0, 360.0)
    return out


def expected_frames(duration_s: float) -> int:
    """Frames of a take, as studio-frames.ts counts them: JS Math.round(seconds * fps).

    Python's round() rounds half to even (5.075 s * 60 = 304.5 -> 304) where Math.round
    rounds half up (305), so the count is floor(x + 0.5).
    """
    return math.floor(duration_s * FPS + 0.5)


def first_frame(t: float) -> int:
    """The first frame at or after `t` seconds of the take."""
    return math.ceil(t * FPS - 1e-9)


def _in_band(point: Sequence[float]) -> bool:
    fx, fy = point[0] / WIDTH, point[1] / HEIGHT
    return PLACES_BAND[0] <= fx <= PLACES_BAND[2] and PLACES_BAND[1] <= fy <= PLACES_BAND[3]


def _track(spec: dict[str, Any], points: dict[str, Any] | None, pid: str, frames: int) -> list:
    if points is None:
        raise CaptureError(f"{spec['id']}: the scene wrote no points")
    track = points.get(pid)
    held = len(track) if isinstance(track, list) else "no"
    if not isinstance(track, list) or len(track) != frames:
        raise CaptureError(
            f"{spec['id']}: points.json holds {held} points for place {pid}, the take has {frames} frames"
        )
    return track


def _place_event(
    cid: str, place: dict[str, Any], track: list, start: int, labelled: bool
) -> dict[str, Any]:
    """The place's event at the first frame from `start` on where the page draws it (inside
    PLACES_BAND when it carries a label), with its track from there to the end of the take."""
    pid = place["id"]
    if start >= len(track):
        raise CaptureError(f"{cid}: place {pid} would light up after the take ends")
    visible = [f for f in range(start, len(track)) if track[f] is not None]
    if not visible:
        raise CaptureError(
            f"{cid}: place {pid} is not visible in the take after {start / FPS:.2f} s "
            "(behind the globe or off screen)"
        )
    if labelled:
        in_band = [f for f in visible if _in_band(track[f])]
        if not in_band:
            fx, fy = track[visible[0]][0] / WIDTH, track[visible[0]][1] / HEIGHT
            raise CaptureError(
                f"{cid}: the page draws place {pid} at ({fx:.2f}, {fy:.2f}) of the frame, "
                f"outside the label band {PLACES_BAND}"
            )
        frame = in_band[0]
        rest = [p if p is not None and _in_band(p) else None for p in track[frame:]]
        extra = {"label": place["label"]}
    else:
        frame = visible[0]
        rest = track[frame:]
        extra = {}
    x, y = track[frame]
    return event(frame / FPS, "place", target=pid, x=x, y=y, track=rest, **extra)


def take_events(
    spec: dict[str, Any], inp: dict[str, Any], points: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Manifest events of a take in time order; pixels are media pixels of the 1920x1080 capture."""
    scene = spec["scene"]
    cid = spec["id"]
    frames = expected_frames(inp["duration_s"])
    if scene == "flyto":
        arrive = inp["rotate_s"] + inp["zoom_s"]
        events = [
            event(0, "rotate"),
            event(inp["rotate_s"], "zoom"),
            event(arrive, "arrive", x=WIDTH / 2, y=HEIGHT / 2),
        ]
        place = spec.get("place")
        if place is None:
            return events
        track = _track(spec, points, place["id"], frames)
        return [*events, _place_event(cid, place, track, first_frame(arrive), labelled=True)]
    if scene == "places":
        # scene_input validated lead_s and interval_s
        lead, interval = float(spec["lead_s"]), float(spec["interval_s"])
        found = [
            _place_event(
                cid,
                place,
                _track(spec, points, place["id"], frames),
                first_frame(lead + i * interval),
                labelled=True,
            )
            for i, place in enumerate(spec["places"])
        ]
        return sorted(found, key=lambda e: e["t"])
    if scene == "distribution":
        found = [
            _place_event(
                cid, place, _track(spec, points, place["id"], frames), 0, labelled="label" in place
            )
            for place in spec["places"]
        ]
        return sorted(found, key=lambda e: e["t"])
    if scene == "mapbox_flyin":
        return [
            event(0, "space"),
            event(FLYIN_ROTATE_S, "zoom"),
            event(FLYIN_ROTATE_S + FLYIN_ZOOM_S, "orbit"),
        ]
    return [event(0, "orbit")]


def recorder_command(npm: str, recorder_scene: str, input_path: Path, out_dir: Path) -> list[str]:
    return [
        npm,
        "run",
        "video:record",
        "--",
        recorder_scene,
        "--fps",
        str(FPS),
        "--input",
        input_path.as_posix(),
        "--out",
        out_dir.as_posix(),
    ]


def start_recorder(cmd: list[str], log: Any) -> subprocess.Popen[bytes]:
    """Start the recorder in the frontend with the production API and its output in `log`."""
    env = {**os.environ, "VITE_DEV_API_TARGET": PRODUCTION_URL}
    return subprocess.Popen(cmd, cwd=FRONTEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)


def _frame_size(frames_dir: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(frames_dir / "f000000.jpg") as first:
        return first.size


def record_globe(episode_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Record one globe or Mapbox take into captures/<id>.mp4 and return its manifest."""
    cid = require_kind(spec, "globe")
    work = media_path(episode_dir, cid, ".rec")
    frames_dir = work / "frames"
    inp = scene_input(spec, work)
    npm = require_tool("npm")
    if spec["scene"].startswith("mapbox_"):
        require_mapbox_token()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    input_path = work / "input.json"
    input_path.write_text(json.dumps(inp, indent=2), encoding="utf-8")
    log_path = work / "recorder.log"
    with display_awake(), log_path.open("wb") as log:
        proc = start_recorder(
            recorder_command(npm, RECORDER_SCENES[spec["scene"]], input_path, work), log
        )
        try:
            proc.wait(timeout=RECORD_TIMEOUT_S)
        except subprocess.TimeoutExpired as err:
            kill_tree(proc)
            raise CaptureError(
                f"{cid}: recorder did not finish in {RECORD_TIMEOUT_S} s; see {log_path}"
            ) from err
    if proc.returncode != 0:
        raise CaptureError(f"{cid}: recorder failed (exit {proc.returncode}); see {log_path}")
    renderer = json.loads((work / "renderer.json").read_text(encoding="utf-8"))["renderer"]
    require_nvidia(renderer, f"{cid}: recorder")
    count = sequence_length(frames_dir)
    if count != expected_frames(inp["duration_s"]):
        raise CaptureError(
            f"{cid}: the take has {count} frames, expected {expected_frames(inp['duration_s'])}"
        )
    size = _frame_size(frames_dir)
    if size != (WIDTH, HEIGHT):
        raise CaptureError(f"{cid}: frames are {size}, expected {(WIDTH, HEIGHT)}")
    points = (
        json.loads((work / "points.json").read_text(encoding="utf-8"))
        if "points_path" in inp
        else None
    )
    events = [gpu_event(renderer), *take_events(spec, inp, points)]
    out = media_path(episode_dir, cid, ".mp4")
    try:
        sequence_to_mp4(frames_dir, FPS, out)
    except subprocess.CalledProcessError as exc:
        raise tool_failure(cid, exc) from exc
    shutil.rmtree(work)
    return build_manifest(
        episode_dir=episode_dir,
        cid=cid,
        kind="globe",
        path=out,
        fps=FPS,
        duration_s=count / FPS,
        width=WIDTH,
        height=HEIGHT,
        events=events,
        credits=CREDITS[spec["scene"]],
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_globe.py -m "not integration and not live_llm" -q -rs`
Expected on the workstation: `28 passed`. Without NVENC (CI): `27 passed, 1 skipped` (the frame-count check now runs before the encode, so only the full take needs NVENC).

- [ ] **Step 5: Lint gate.** Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/globe.py tests/pipeline/studio/capture/test_capture_globe.py
git commit -m "Record globe and Mapbox takes frame by frame through the recorder and prove they ran on the NVIDIA" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 32: The capture contract's four functions

**Files:**
- Modify: `pipeline/studio/capture/__init__.py` (replace the Task 23 docstring stub)
- Test: `tests/pipeline/studio/capture/test_capture_package.py`

Plan C's `captures.py` imports `record_platform`, `record_globe`, `capture_source` and `mapbox_topdown` from the package itself (`default_recorders`). The package now imports `sources.py` whenever any of its modules is imported, so this task starts only after Task 29 (and therefore check A2) has landed.

- [ ] **Step 1: Write the failing test**

**`tests/pipeline/studio/capture/test_capture_package.py`** (complete file):

```python
"""The package surface plan C's captures.py calls (contract C7)."""

import inspect

from pipeline.studio import capture


def test_the_four_contract_functions_are_importable_from_the_package():
    names = {
        "platform": "record_platform",
        "globe": "record_globe",
        "source": "capture_source",
        "mapbox_topdown": "mapbox_topdown",
    }
    for name in names.values():
        fn = getattr(capture, name)
        assert list(inspect.signature(fn).parameters) == ["episode_dir", "spec"]
    assert sorted(capture.__all__) == sorted(names.values())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture/test_capture_package.py -m "not integration and not live_llm" -q -rs`
Expected: FAIL with `AttributeError: module 'pipeline.studio.capture' has no attribute 'record_platform'`.

- [ ] **Step 3: Implement**

**`pipeline/studio/capture/__init__.py`** (complete file):

```python
"""Studio captures (spec 2026-09-26 section 4.5; plan C contract C7).

Four entry points, each ``(episode_dir: Path, spec: dict) -> dict``. ``spec`` is the
script's capture entry ``{"id", "kind", ...}``; each function writes its media as
``captures/<id>.<ext>`` in the episode workspace and returns the manifest
(manifest.py), which ``pipeline.studio.captures`` validates and stores as
``captures/<id>.json``:

* record_platform  kind "platform"        real site take (Playwright CDP screencast)
* record_globe     kind "globe"           our vector globe or a Mapbox take (Puppeteer recorder)
* capture_source   kind "source"          a source page, or our paper page, with the quote highlighted
* mapbox_topdown   kind "mapbox_topdown"  Mapbox Static top-down frame with projected pins

Local-only: Playwright, Chrome, Node and ffmpeg live on the workstation and are
imported or started inside the functions. Nothing in api/ or pipeline/lyra imports
this package.
"""

from pipeline.studio.capture.globe import record_globe
from pipeline.studio.capture.mapbox import mapbox_topdown
from pipeline.studio.capture.platform import record_platform
from pipeline.studio.capture.sources import capture_source

__all__ = ["capture_source", "mapbox_topdown", "record_globe", "record_platform"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture -m "not integration and not live_llm" -q -rs`
Expected on the workstation: `142 passed, 1 skipped` (the non-Windows refusal test). Without the NVIDIA driver and Playwright (CI): `129 passed, 14 skipped`, each skip with its reason.

- [ ] **Step 5: Lint gate.** Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add pipeline/studio/capture/__init__.py tests/pipeline/studio/capture/test_capture_package.py
git commit -m "Export the four capture functions plan C's capture step calls" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 33: The frontend's `?video=1` capture mode

**Files:**
- Create: `ancient-nerds-map/src/utils/videoMode.ts`
- Modify: `ancient-nerds-map/src/App.tsx` (import, one effect, one line in `armGlobeIdle`), `ancient-nerds-map/src/components/Globe.tsx` (HUD scale from `?hud=`)
- Test: `ancient-nerds-map/src/utils/__tests__/videoMode.test.ts`

Spec 4.6 (contract D5). The platform takes open `globe.html?demo=1&video=1&hud=1.3`: the options panel (FPS counter, database and connector status), the social/contribute buttons, hover tooltips (not the selected site's label, which carries the same class and is the answer of a search moment), warning banners and the native cursor disappear (the take draws its own NERV cursor), the HUD scale reads on video, and `window.__VIDEO.ready` turns true at globe_ready, so the take never films the loading overlay. The mode reads only the query string; nothing touches browser storage (the SSR rule). `armGlobeIdle` keeps its name: `src/hooks/__tests__/globeReadyWiring.test.ts` pins the `useGlobeReady(...)` call.

- [ ] **Step 1: Write the failing test**

**`ancient-nerds-map/src/utils/__tests__/videoMode.test.ts`** (complete file):

```ts
/**
 * ?video=1 is the studio's capture mode (pipeline/studio/capture/platform.py):
 * panels and tooltips hidden, ?hud= scale, window.__VIDEO.ready at globe_ready.
 * It reads only the query string, never browser storage.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  HUD_MAX,
  VIDEO_MODE_CLASS,
  VIDEO_MODE_CSS,
  applyVideoMode,
  markVideoReady,
  parseVideoMode,
} from '../videoMode'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('parseVideoMode', () => {
  it('is off without ?video=1, even with ?hud=', () => {
    expect(parseVideoMode('')).toEqual({ enabled: false, hudScale: null })
    expect(parseVideoMode('?demo=1&hud=1.3')).toEqual({ enabled: false, hudScale: null })
    expect(parseVideoMode('?video=0')).toEqual({ enabled: false, hudScale: null })
  })

  it('reads the HUD scale next to demo mode', () => {
    expect(parseVideoMode('?demo=1&video=1')).toEqual({ enabled: true, hudScale: null })
    expect(parseVideoMode('?demo=1&video=1&hud=1.3')).toEqual({ enabled: true, hudScale: 1.3 })
  })

  it.each(['abc', '', '0.2', String(HUD_MAX + 1)])('rejects ?hud=%s', (hud) => {
    expect(() => parseVideoMode(`?video=1&hud=${hud}`)).toThrow(/expected a number between/)
  })
})

function fakeDom() {
  const classes = new Set<string>()
  const appended: { id: string; textContent: string; remove: () => void }[] = []
  const style = { id: '', textContent: '', remove: vi.fn() }
  const doc = {
    createElement: vi.fn(() => style),
    head: { appendChild: vi.fn((el: typeof style) => appended.push(el)) },
    body: { classList: { add: (c: string) => classes.add(c), remove: (c: string) => classes.delete(c) } },
  }
  return { doc: doc as unknown as Document, classes, appended, style }
}

describe('applyVideoMode', () => {
  it('does nothing outside video mode', () => {
    const { doc, classes } = fakeDom()
    const win = {} as Window
    applyVideoMode({ enabled: false, hudScale: null }, doc, win)()
    expect(classes.size).toBe(0)
    expect(win.__VIDEO).toBeUndefined()
  })

  it('adds the style and body class, exposes __VIDEO and undoes it all', () => {
    const { doc, classes, appended, style } = fakeDom()
    const win = {} as Window
    const cleanup = applyVideoMode({ enabled: true, hudScale: 1.3 }, doc, win)
    expect(classes.has(VIDEO_MODE_CLASS)).toBe(true)
    expect(appended[0].textContent).toBe(VIDEO_MODE_CSS)
    expect(win.__VIDEO).toEqual({ ready: false, hudScale: 1.3 })
    markVideoReady(win)
    expect(win.__VIDEO?.ready).toBe(true)
    cleanup()
    expect(classes.has(VIDEO_MODE_CLASS)).toBe(false)
    expect(style.remove).toHaveBeenCalledOnce()
    expect(win.__VIDEO).toBeUndefined()
  })

  it('hides the panels the spec names and the native cursor', () => {
    for (const selector of ['.info-panel-top-right', '.social-contribute-wrapper', '.fps-display-container', '.site-hover-tooltip']) {
      expect(VIDEO_MODE_CSS).toContain(`body.video-mode ${selector}`)
    }
    expect(VIDEO_MODE_CSS).toContain('cursor: none !important')
  })

  it('keeps the label of the selected site (the answer of a search moment), hiding only hover tooltips', () => {
    expect(VIDEO_MODE_CSS).toContain('body.video-mode .site-hover-tooltip:not(.selected-site-label)')
    expect(VIDEO_MODE_CSS).not.toMatch(/\.site-hover-tooltip,/)
  })

  it('never touches browser storage', () => {
    const trap = new Proxy({}, { get: () => { throw new Error('storage touched') } })
    vi.stubGlobal('localStorage', trap)
    vi.stubGlobal('sessionStorage', trap)
    const { doc } = fakeDom()
    const win = {} as Window
    applyVideoMode(parseVideoMode('?video=1&hud=1.2'), doc, win)
    markVideoReady(win)
    expect(win.__VIDEO?.ready).toBe(true)
  })
})

describe('markVideoReady', () => {
  it('is a no-op outside video mode', () => {
    const win = {} as Window
    markVideoReady(win)
    expect(win.__VIDEO).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ancient-nerds-map && npx vitest run src/utils/__tests__/videoMode.test.ts`
Expected: FAIL with `Cannot find module '../videoMode'`.

- [ ] **Step 3: Implement**

**`ancient-nerds-map/src/utils/videoMode.ts`** (complete file):

```ts
/**
 * Studio capture mode, `?video=1` (next to `?demo=1`): the globe as the
 * platform takes of pipeline/studio/capture/platform.py record it
 * (spec docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md 4.6).
 *
 * - hides the options panel (FPS counter, database/connector status), the
 *   social/contribute buttons, the hover tooltips and the native cursor (the
 *   capture injects its own NERV cursor);
 * - `?hud=1.3` sets the HUD scale (--hud-scale) so the UI reads on video;
 * - window.__VIDEO.ready turns true at globe_ready, when a visitor would see
 *   the globe (App.tsx), so the capture never films the loading overlay.
 *
 * Only query parameters are read: no browser storage, nothing on import, safe
 * in every render path.
 */

export interface VideoMode {
  enabled: boolean
  /** From ?hud=, null keeps the HUD's own default. */
  hudScale: number | null
}

export interface VideoState {
  ready: boolean
  hudScale: number | null
}

declare global {
  interface Window {
    __VIDEO?: VideoState
  }
}

export const HUD_MIN = 0.5
export const HUD_MAX = 2
export const VIDEO_MODE_CLASS = 'video-mode'
const STYLE_ID = 'video-mode-style'

/**
 * Hidden in video mode; class names verified against the components (OptionsPanel,
 * SocialLinks, Globe). The label of the selected site also carries .site-hover-tooltip
 * (TooltipOverlay.tsx: "site-hover-tooltip selected-site-label"); after click_result it
 * is the answer of the take, so only hover tooltips are hidden.
 */
export const VIDEO_MODE_HIDDEN = [
  '.info-panel-top-right',
  '.social-contribute-wrapper',
  '.fps-display-container',
  '.database-status-indicator',
  '.connectors-status-indicator',
  '.site-hover-tooltip:not(.selected-site-label)',
  '.fps-warning-tooltip',
  '.hardware-warning-banner',
] as const

export const VIDEO_MODE_CSS =
  `${VIDEO_MODE_HIDDEN.map((s) => `body.${VIDEO_MODE_CLASS} ${s}`).join(',\n')} { display: none !important; }\n` +
  `body.${VIDEO_MODE_CLASS}, body.${VIDEO_MODE_CLASS} * { cursor: none !important; }`

/** Read the mode from a query string; an out-of-range ?hud= is an error, not a silent default. */
export function parseVideoMode(search: string): VideoMode {
  const params = new URLSearchParams(search)
  if (params.get('video') !== '1') return { enabled: false, hudScale: null }
  const raw = params.get('hud')
  if (raw === null) return { enabled: true, hudScale: null }
  const hud = Number(raw)
  if (raw.trim() === '' || !Number.isFinite(hud) || hud < HUD_MIN || hud > HUD_MAX) {
    throw new Error(`?hud=${raw}: expected a number between ${HUD_MIN} and ${HUD_MAX}`)
  }
  return { enabled: true, hudScale: hud }
}

/** Switch video mode on (style + body class + window.__VIDEO); returns the cleanup. */
export function applyVideoMode(mode: VideoMode, doc: Document, win: Window): () => void {
  if (!mode.enabled) return () => undefined
  const style = doc.createElement('style')
  style.id = STYLE_ID
  style.textContent = VIDEO_MODE_CSS
  doc.head.appendChild(style)
  doc.body.classList.add(VIDEO_MODE_CLASS)
  win.__VIDEO = { ready: false, hudScale: mode.hudScale }
  return () => {
    style.remove()
    doc.body.classList.remove(VIDEO_MODE_CLASS)
    delete win.__VIDEO
  }
}

/** globe_ready: the capture may start. A no-op outside video mode. */
export function markVideoReady(win: Window): void {
  if (win.__VIDEO) win.__VIDEO.ready = true
}
```

In `ancient-nerds-map/src/App.tsx`, replace:

```tsx
import { isDemoMode, registerAppDemoApi } from './utils/demoApi'
```

with:

```tsx
import { isDemoMode, registerAppDemoApi } from './utils/demoApi'
import { applyVideoMode, markVideoReady, parseVideoMode } from './utils/videoMode'
```

In `ancient-nerds-map/src/App.tsx`, replace:

```tsx
    registerAppDemoApi({ setFilterMode, setAgeRange, setFlyToCoords, setDemoMode, setSelectedSources, handleLoadSources, openSitePopup, closeAllPopups, sitesRef })
  }, [])

```

with:

```tsx
    registerAppDemoApi({ setFilterMode, setAgeRange, setFlyToCoords, setDemoMode, setSelectedSources, handleLoadSources, openSitePopup, closeAllPopups, sitesRef })
  }, [])

  // Studio capture mode (?video=1): panels hidden, ?hud= scale, window.__VIDEO (utils/videoMode.ts)
  useEffect(() => applyVideoMode(parseVideoMode(window.location.search), document, window), [])

```

In `ancient-nerds-map/src/App.tsx`, replace:

```tsx
  const armGlobeIdle = useCallback(() => {
    idleTimerRef.current = setTimeout(() => track('globe_idle', { ms: 30000 }), 30000)
  }, [])
```

with:

```tsx
  const armGlobeIdle = useCallback(() => {
    idleTimerRef.current = setTimeout(() => track('globe_idle', { ms: 30000 }), 30000)
    // studio captures (?video=1) start filming here (utils/videoMode.ts)
    markVideoReady(window)
  }, [])
```

In `ancient-nerds-map/src/components/Globe.tsx`, replace:

```tsx
import { isDemoMode, registerGlobeDemoApi } from '../utils/demoApi'
```

with:

```tsx
import { isDemoMode, registerGlobeDemoApi } from '../utils/demoApi'
import { parseVideoMode } from '../utils/videoMode'
```

In `ancient-nerds-map/src/components/Globe.tsx`, replace:

```tsx
  const ui = useUIState({ initialShowCoordinates: true })
```

with:

```tsx
  // ?video=1&hud=1.3: the studio capture's HUD scale (utils/videoMode.ts); otherwise the HUD default
  const [videoHudScale] = useState(() => parseVideoMode(window.location.search).hudScale)
  const ui = useUIState({ initialShowCoordinates: true, ...(videoHudScale === null ? {} : { initialHudScale: videoHudScale }) })
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ancient-nerds-map && npx vitest run src/utils/__tests__/videoMode.test.ts src/hooks/__tests__/globeReadyWiring.test.ts && npm run type-check`
Expected: `Tests  20 passed (20)` (12 new, 8 wiring), then `tsc --noEmit` with no errors.

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/src/utils/videoMode.ts ancient-nerds-map/src/utils/__tests__/videoMode.test.ts ancient-nerds-map/src/App.tsx ancient-nerds-map/src/components/Globe.tsx
git commit -m "Add the globe's ?video=1 capture mode: panels hidden, HUD scale from ?hud=, a ready flag at globe_ready" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 34: `window.__DEMO.screenPoint`: where the page draws a place

**Files:**
- Create: `ancient-nerds-map/src/utils/screenPoint.ts`
- Modify: `ancient-nerds-map/src/utils/demoApi.ts`, `ancient-nerds-map/src/components/Globe.tsx`, `ancient-nerds-map/video/record.ts`
- Test: `ancient-nerds-map/src/utils/__tests__/screenPoint.test.ts`

The globe takes light places up where the page itself draws them, and the platform take clicks the Measure tool's points exactly (spec 4.5). `screenPoint(lat, lng)` answers from Mapbox's `project()` while Mapbox is shown, else from the Three.js camera (a unit-sphere point faces a camera at C exactly when p · C > 1); null when the place is hidden or off screen. The recorder proxies it like every other demo call.

- [ ] **Step 1: Write the failing test**

**`ancient-nerds-map/src/utils/__tests__/screenPoint.test.ts`** (complete file):

```ts
/**
 * window.__DEMO.screenPoint: where the page draws a place, for the studio's
 * globe pins and the platform take's measure clicks.
 */
import * as THREE from 'three'
import { describe, expect, it } from 'vitest'

import { latLngToPosition } from '../geoUtils'
import { globeScreenPoint, viewportPoint } from '../screenPoint'

function cameraAbove(lat: number, lng: number, distance: number, fov = 60): THREE.PerspectiveCamera {
  const camera = new THREE.PerspectiveCamera(fov, 1920 / 1080, 0.01, 1500)
  camera.position.copy(latLngToPosition(lng, lat, distance))
  camera.lookAt(0, 0, 0)
  camera.updateMatrixWorld()
  camera.updateProjectionMatrix()
  return camera
}

describe('globeScreenPoint', () => {
  it('puts the point under the camera at the viewport centre', () => {
    const p = globeScreenPoint(cameraAbove(34, 36.2, 1.8), 34, 36.2, 1920, 1080)
    expect(p?.x).toBeCloseTo(960, 3)
    expect(p?.y).toBeCloseTo(540, 3)
  })
  it('puts points east to the right and north up', () => {
    const camera = cameraAbove(0, 0, 2)
    const east = globeScreenPoint(camera, 0, 10, 1920, 1080)
    const north = globeScreenPoint(camera, 10, 0, 1920, 1080)
    expect(east && east.x > 960).toBe(true)
    expect(north && north.y < 540).toBe(true)
  })
  it('narrows with the telephoto FOV: the same place lies further from the centre', () => {
    const wide = globeScreenPoint(cameraAbove(34, 36.2, 1.35, 60), 33, 36.2, 1920, 1080)
    const tele = globeScreenPoint(cameraAbove(34, 36.2, 1.35, 15.1), 33, 36.2, 1920, 1080)
    expect(wide && tele && tele.y - 540 > 3 * (wide.y - 540)).toBe(true)
  })
  it('hides the far side of the globe and points outside the viewport', () => {
    expect(globeScreenPoint(cameraAbove(0, 0, 2), 0, 180, 1920, 1080)).toBeNull()
    expect(globeScreenPoint(cameraAbove(34, 36.2, 1.35, 15.1), 10, 36.2, 1920, 1080)).toBeNull()
  })
})

describe('viewportPoint', () => {
  it('keeps points inside the viewport only', () => {
    expect(viewportPoint({ x: 10, y: 20 }, 1920, 1080)).toEqual({ x: 10, y: 20 })
    expect(viewportPoint({ x: -1, y: 20 }, 1920, 1080)).toBeNull()
    expect(viewportPoint({ x: 10, y: 1081 }, 1920, 1080)).toBeNull()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ancient-nerds-map && npx vitest run src/utils/__tests__/screenPoint.test.ts`
Expected: FAIL with `Cannot find module '../screenPoint'`.

- [ ] **Step 3: Implement**

**`ancient-nerds-map/src/utils/screenPoint.ts`** (complete file):

```ts
/**
 * Viewport pixel of a place in the current view, for the studio captures
 * (window.__DEMO.screenPoint, pipeline/studio/capture): the globe take marks
 * places where the page itself draws them, the platform take clicks measure
 * points exactly. Pure; the camera or Mapbox's project() is passed in.
 */
import type * as THREE from 'three'

import { latLngToPosition } from './geoUtils'

export type ScreenPoint = { x: number; y: number }

/** The point when it lies inside the width x height viewport, else null. */
export function viewportPoint(p: ScreenPoint, width: number, height: number): ScreenPoint | null {
  return p.x >= 0 && p.x <= width && p.y >= 0 && p.y <= height ? { x: p.x, y: p.y } : null
}

/**
 * Pixel of a surface point for the Three.js globe camera (unit globe at the
 * origin); null behind the horizon or outside the viewport. A point p of the
 * unit sphere faces a camera at C (|C| > 1) exactly when p . C > 1.
 */
export function globeScreenPoint(camera: THREE.Camera, lat: number, lng: number, width: number, height: number): ScreenPoint | null {
  const p = latLngToPosition(lng, lat, 1)
  if (p.dot(camera.position) <= 1) return null
  const v = p.clone().project(camera)
  return viewportPoint({ x: ((v.x + 1) / 2) * width, y: ((1 - v.y) / 2) * height }, width, height)
}
```

In `ancient-nerds-map/src/utils/demoApi.ts`, replace:

```ts
import type { MapboxLoadState } from '../services/mapboxLoader'
```

with:

```ts
import type { MapboxLoadState } from '../services/mapboxLoader'
import type { ScreenPoint } from './screenPoint'
```

In `ancient-nerds-map/src/utils/demoApi.ts`, replace:

```ts
  getCameraState(): CameraState | Promise<CameraState>
  isReady(): boolean
```

with:

```ts
  getCameraState(): CameraState | Promise<CameraState>
  /**
   * Viewport pixel of a place in the current view (Mapbox when it is shown, the
   * globe camera otherwise); null when the place is hidden or off screen. The
   * studio captures mark and click places with it (utils/screenPoint.ts).
   */
  screenPoint(lat: number, lng: number): ScreenPoint | null | Promise<ScreenPoint | null>
  isReady(): boolean
```

In `ancient-nerds-map/src/utils/demoApi.ts`, replace:

```ts
  /** Moves the Mapbox task to the front of the globe's background queue. */
  requestMapbox: () => void
}
```

with:

```ts
  /** Moves the Mapbox task to the front of the globe's background queue. */
  requestMapbox: () => void
  /** Viewport pixel of a place in the current view (DemoAPI.screenPoint). */
  screenPoint: (lat: number, lng: number) => ScreenPoint | null
}
```

In `ancient-nerds-map/src/utils/demoApi.ts`, replace:

```ts
    getCameraState: () => {
      const scene = refs.sceneRef.current
```

with:

```ts
    screenPoint: (lat, lng) => refs.screenPoint(lat, lng),
    getCameraState: () => {
      const scene = refs.sceneRef.current
```

In `ancient-nerds-map/src/components/Globe.tsx`, replace:

```tsx
import { parseVideoMode } from '../utils/videoMode'
```

with:

```tsx
import { globeScreenPoint, viewportPoint } from '../utils/screenPoint'
import { parseVideoMode } from '../utils/videoMode'
```

In `ancient-nerds-map/src/components/Globe.tsx`, replace:

```tsx
      requestMapbox: () => { background.promote('mapbox') },
    })
```

with:

```tsx
      requestMapbox: () => { background.promote('mapbox') },
      screenPoint: (lat, lng) => {
        if (showMapboxRef.current) {
          const map = mapboxServiceRef.current?.getMap()
          if (!map) throw new Error('screenPoint: Mapbox is shown but has no map')
          return viewportPoint(map.project([lng, lat]), window.innerWidth, window.innerHeight)
        }
        if (!sceneRef.current) return null
        return globeScreenPoint(sceneRef.current.camera, lat, lng, window.innerWidth, window.innerHeight)
      },
    })
```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
import type { CameraState, DemoAPI } from '../src/utils/demoApi'
```

with:

```ts
import type { CameraState, DemoAPI } from '../src/utils/demoApi'
import type { ScreenPoint } from '../src/utils/screenPoint'
```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
    getCameraState: () => page.evaluate('window.__DEMO.getCameraState()') as Promise<CameraState>,
```

with:

```ts
    getCameraState: () => page.evaluate('window.__DEMO.getCameraState()') as Promise<CameraState>,
    screenPoint: (lat, lng) => page.evaluate(`window.__DEMO.screenPoint(${lat}, ${lng})`) as Promise<ScreenPoint | null>,
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ancient-nerds-map && npx vitest run src/utils/__tests__/screenPoint.test.ts src/utils/__tests__/demoApi.test.ts && npm run type-check && npx tsc -p video/tsconfig.json --noEmit`
Expected: `Tests  9 passed (9)` (5 new, 4 demo API), then both type checks without errors.

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/src/utils/screenPoint.ts ancient-nerds-map/src/utils/__tests__/screenPoint.test.ts ancient-nerds-map/src/utils/demoApi.ts ancient-nerds-map/src/components/Globe.tsx ancient-nerds-map/video/record.ts
git commit -m "Expose where the page draws a place, on the globe or on Mapbox, to the studio captures" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 35: The recorder's studio scenes

**Files:**
- Create: `ancient-nerds-map/video/scenes/studio-frames.ts`, `ancient-nerds-map/video/scenes/studio-globe.ts`, `ancient-nerds-map/video/scenes/studio-mapbox.ts`
- Modify: `ancient-nerds-map/video/scenes/site-short.ts` (exports only), `ancient-nerds-map/video/record.ts` (registration)
- Test: `ancient-nerds-map/video/scenes/__tests__/studio-scenes.test.ts`

Contract D6. The studio scenes grab every frame themselves (`FrameGrabber`): tick the synthetic clock, wait two animation frames (bounded at 30 s: a display that stopped drawing fails the take with that reason instead of hanging), wait for Mapbox tiles when needed, read the canvas as JPEG. They first write the page's WebGL renderer to `renderer.json` for `globe.py` (spec 4.11; the recorder launches Chrome with the NVIDIA flags). Places are projected per frame (owner rule): after every grabbed frame a `PointTracker` reads `window.__DEMO.screenPoint` for every place in one page call, and `points.json` holds one `[x, y]` or null per frame and place; a places take with `sweep_lng_deg` sets the camera longitude before every frame (`sweepLng`), so its pins move with the globe, and a `distribution` take is such a sweep of 360 degrees. The globe scenes stay at distance 1.2 or more, outside the Mapbox hand-off (1.12), so they show only our vector globe. The Mapbox scenes reuse the site shorts' look and tile warm-up (`prepareMapbox`, `warmPath`, now exported from `site-short.ts` without a behaviour change); in landscape the space pose uses zoom 2.4, which fills about 80 % of the frame height (the portrait value 2.2 left the globe small, 2026-09-26). A Mapbox take's `country` is shown data (its outline is highlighted): `prepareMapbox` only logs "no highlight" for a name `getCountryCode` does not know, which suits the Shorts, so the studio scenes refuse such a name first (`checkCountry`: `unknown country <x>`; the recorder exits 1 and `globe.py` raises its `CaptureError`), and plan C binds the value to the site export. `record.ts` registers the four scenes, exposes the scene input as `STUDIO_SCENE_INPUT`, skips its MediaRecorder stop and encode for scenes that grab their own frames, and starts Vite with `--strictPort`: during planning a dev server orphaned by an interrupted take kept port 5199 for hours, the next recorder's Vite silently moved to another port and the takes were served by the orphan's (older) checkout.

- [ ] **Step 1: Write the failing test**

**`ancient-nerds-map/video/scenes/__tests__/studio-scenes.test.ts`** (complete file):

```ts
/**
 * Pure input, path and frame logic of the studio recorder scenes
 * (video/scenes/studio-globe.ts, studio-mapbox.ts, studio-frames.ts). The takes
 * themselves need headed Chrome and run only on the workstation
 * (pipeline/studio/capture/globe.py).
 */

import { mkdtempSync, readFileSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import type { Page } from 'puppeteer'

import { afterEach, describe, expect, it } from 'vitest'

import { FrameGrabber, NO_FRAME_MS, PointTracker, frameCount, frameName } from '../studio-frames'
import { type PlacesInput, START_LNG_OFFSET, flytoStart, readStudioInput, sweepLng } from '../studio-globe'
import { ORBIT_BEARING_TO, ROTATE_S, SPACE_ZOOM, ZOOM_S, checkCountry, flyinPath, orbitPath } from '../studio-mapbox'

const saved = process.env.STUDIO_SCENE_INPUT

afterEach(() => {
  if (saved === undefined) delete process.env.STUDIO_SCENE_INPUT
  else process.env.STUDIO_SCENE_INPUT = saved
})

function writeInput(data: object): string {
  const file = join(mkdtempSync(join(tmpdir(), 'studio-scene-')), 'input.json')
  writeFileSync(file, JSON.stringify(data))
  return file
}

describe('readStudioInput', () => {
  it('reads the input of the matching scene', () => {
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'places', cam_lat: 30, cam_lng: 20, distance: 1.8, duration_s: 6, frames_dir: '/tmp/f', renderer_path: '/tmp/r.json' })
    expect(readStudioInput<PlacesInput>('places').duration_s).toBe(6)
  })
  it('refuses a missing variable, another scene, a non-positive duration and missing output paths', () => {
    delete process.env.STUDIO_SCENE_INPUT
    expect(() => readStudioInput('flyto')).toThrow(/STUDIO_SCENE_INPUT not set/)
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'places', duration_s: 6, frames_dir: '/tmp/f', renderer_path: '/tmp/r.json' })
    expect(() => readStudioInput('flyto')).toThrow(/holds a places input, the scene needs flyto/)
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'flyto', duration_s: 0, frames_dir: '/tmp/f', renderer_path: '/tmp/r.json' })
    expect(() => readStudioInput('flyto')).toThrow(/duration_s must be positive/)
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'flyto', duration_s: 5, renderer_path: '/tmp/r.json' })
    expect(() => readStudioInput('flyto')).toThrow(/frames_dir is missing/)
    process.env.STUDIO_SCENE_INPUT = writeInput({ scene: 'flyto', duration_s: 5, frames_dir: '/tmp/f' })
    expect(() => readStudioInput('flyto')).toThrow(/renderer_path is missing/)
  })
})

describe('studio-globe-flyto', () => {
  it('starts west and north of the target, away from the poles', () => {
    expect(flytoStart({ lat: 34, lng: 36.2 })).toEqual({ lng: 36.2 + START_LNG_OFFSET, lat: 49 })
    expect(flytoStart({ lat: 68, lng: 0 }).lat).toBe(70)
  })
})

describe('studio-globe-places sweep', () => {
  it('turns the camera linearly over the take and keeps the longitude in -180..180', () => {
    expect(sweepLng(-10, 120, 0, 60, 6)).toBe(-10)
    expect(sweepLng(-10, 120, 90, 60, 6)).toBe(20)
    expect(sweepLng(170, 40, 60, 60, 2)).toBe(-170)
  })
})

describe('PointTracker (points.json)', () => {
  const places = [
    { id: 'p1', lat: 34, lng: 36.2 },
    { id: 'p2', lat: 29.98, lng: 31.13 },
  ]
  it('keeps one pixel or null per grabbed frame and place, read in one page call', async () => {
    const answers = [
      [{ x: 1, y: 2 }, null],
      [
        { x: 3, y: 4 },
        { x: 5, y: 6 },
      ],
    ]
    const calls: string[] = []
    const page = { evaluate: async (code: string) => (calls.push(code), answers[calls.length - 1]) } as unknown as Page
    const tracker = new PointTracker(places)
    await tracker.sample(page)
    await tracker.sample(page)
    expect(calls).toHaveLength(2)
    expect(calls[0]).toContain('window.__DEMO.screenPoint')
    const file = join(mkdtempSync(join(tmpdir(), 'studio-points-')), 'points.json')
    tracker.write(file, 2)
    expect(JSON.parse(readFileSync(file, 'utf-8'))).toEqual({ p1: [[1, 2], [3, 4]], p2: [null, [5, 6]] })
    expect(() => tracker.write(file, 3)).toThrow(/place p1: 2 points for 3 frames/)
  })
})

describe('studio-mapbox-flyin', () => {
  const input = { lat: 34.0067, lng: 36.2033, orbit_zoom: 15, duration_s: 8 }
  it('rotates onto the site, zooms in, then orbits to the end of the take', () => {
    const path = flyinPath(input)
    expect(path.map((k) => k.at)).toEqual([0, ROTATE_S / 8, (ROTATE_S + ZOOM_S) / 8, 1])
    expect(path[0]).toMatchObject({ zoom: SPACE_ZOOM, terrain: null })
    expect(path[1]).toMatchObject({ lng: 36.2033, lat: 34.0067, zoom: SPACE_ZOOM })
    expect(path[3]).toMatchObject({ lng: 36.2033, lat: 34.0067, zoom: 15, bearing: ORBIT_BEARING_TO })
  })
  it('refuses a take too short for rotate + zoom + a second of orbit', () => {
    expect(() => flyinPath({ ...input, duration_s: 4 })).toThrow(/needs at least 4.6 s/)
  })
})

describe('Mapbox country highlight', () => {
  it('refuses a country the site cannot highlight instead of recording the take without it', () => {
    expect(() => checkCountry(undefined)).not.toThrow()
    expect(() => checkCountry('Lebanon')).not.toThrow()
    expect(() => checkCountry('Atlantis')).toThrow(/unknown country "Atlantis"/)
  })
})

describe('studio-mapbox-orbit', () => {
  it('sweeps the bearing around a fixed centre with terrain', () => {
    expect(orbitPath({ lat: 1, lng: 2, zoom: 16, pitch: 55, bearing_from: 0, bearing_to: 90 })).toEqual([
      { at: 0, lng: 2, lat: 1, zoom: 16, pitch: 55, bearing: 0, terrain: 1.4 },
      { at: 1, lng: 2, lat: 1, zoom: 16, pitch: 55, bearing: 90 },
    ])
  })
})

describe('exact frames', () => {
  it('names frames for ffmpeg and counts them to the nearest frame', () => {
    expect(frameName(0)).toBe('f000000.jpg')
    expect(frameName(1234)).toBe('f001234.jpg')
    expect(() => frameName(-1)).toThrow(/not a non-negative integer/)
    expect(frameCount(1.5, 60)).toBe(90)
    expect(frameCount(3.5, 60)).toBe(210)
    expect(() => frameCount(0, 60)).toThrow(/cannot count frames/)
  })
  it('gives up on a missing animation frame after 30 s', () => {
    expect(NO_FRAME_MS).toBe(30_000)
  })
  it('refuses a frames directory that already holds frames', () => {
    const dir = mkdtempSync(join(tmpdir(), 'studio-frames-'))
    writeFileSync(join(dir, frameName(0)), 'x')
    expect(() => new FrameGrabber(dir, '.globe-container canvas', false)).toThrow(/is not empty/)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ancient-nerds-map && npx vitest run video/scenes/__tests__/studio-scenes.test.ts`
Expected: FAIL with `Cannot find module '../studio-frames'`.

- [ ] **Step 3: Implement**

In `ancient-nerds-map/video/scenes/site-short.ts`, replace:

```ts
interface SiteInput {
```

with:

```ts
export interface SiteInput {
```

In `ancient-nerds-map/video/scenes/site-short.ts`, replace:

```ts
const TERRAIN_EXAGGERATION = 1.4
```

with:

```ts
export const TERRAIN_EXAGGERATION = 1.4
```

In `ancient-nerds-map/video/scenes/site-short.ts`, replace:

```ts
async function prepareMapbox(ctx: SceneContext, site: SiteInput): Promise<void> {
```

with:

```ts
export async function prepareMapbox(ctx: SceneContext, site: SiteInput): Promise<void> {
```

In `ancient-nerds-map/video/scenes/site-short.ts`, replace:

```ts
/** Warm the tile/DEM cache along the path, reset to its first pose, then capture. */
async function recordPath(ctx: SceneContext, path: MapboxKeyframe[], seconds: number): Promise<void> {
  const { page, demo, fire, recorder } = ctx
```

with:

```ts
/** Warm the tile/DEM cache along the path and reset to its first pose (studio-mapbox.ts shares it). */
export async function warmPath(ctx: SceneContext, path: MapboxKeyframe[], seconds: number): Promise<void> {
  const { page, demo } = ctx
```

In `ancient-nerds-map/video/scenes/site-short.ts`, replace:

```ts
  await settle(page)
  fire(`window.__DEMO.mapboxPath(${JSON.stringify(path)}, ${seconds * 1000})`)
  await recorder.capture(page, seconds)
}
```

with:

```ts
  await settle(page)
}

/** Warm the path, then fly it while the recorder captures. */
async function recordPath(ctx: SceneContext, path: MapboxKeyframe[], seconds: number): Promise<void> {
  await warmPath(ctx, path, seconds)
  ctx.fire(`window.__DEMO.mapboxPath(${JSON.stringify(path)}, ${seconds * 1000})`)
  await ctx.recorder.capture(ctx.page, seconds)
}
```

**`ancient-nerds-map/video/scenes/studio-frames.ts`** (complete file):

```ts
/**
 * Exact frame capture for the studio scenes (studio-globe.ts, studio-mapbox.ts).
 *
 * The recorder's StreamRecorder (canvas.captureStream(0) + MediaRecorder) drops
 * frames whenever the VP8 encoder falls behind, and utils/encode.ts then
 * stretches whatever arrived to the take length. Measured 2026-09-26 on the
 * workstation (RTX 3080, 1920x1080 @ 60 fps, frameYieldMs 0): 22, 66 and 0 of
 * 300 requested frames for studio-globe-flyto; 38 of 240 for empire-han. The
 * 0-frame take is an empty WebM, which is the "EBML header parsing failed"
 * error of the first studio capture. The studio needs every frame at its
 * exact time (pins are placed on event times), so these scenes grab each
 * frame themselves: tick the synthetic clock, let the globe draw, read the
 * canvas as JPEG, write f000000.jpg, f000001.jpg, ... into the frames
 * directory named by the scene input. pipeline/studio/capture/globe.py turns
 * the numbered frames into a constant-rate clip and checks the count.
 *
 * Headed Chrome draws only while the Windows display is on and the session
 * unlocked: a take whose display slept waited 15 minutes for its first frame
 * (2026-09-26). Every wait for an animation frame is therefore bounded by
 * NO_FRAME_MS and fails with that reason (globe.py also holds the display awake).
 *
 * Both canvases keep their drawing buffer in demo mode (Three.js:
 * globeConstants preserveDrawingBuffer; Mapbox: MapboxGlobeService with
 * isDemoMode()), so toDataURL reads the frame just drawn.
 */

import { mkdirSync, readdirSync, writeFileSync } from 'fs'
import { join } from 'path'
import type { Page } from 'puppeteer'
import type { ScreenPoint } from '../../src/utils/screenPoint'
import type { SceneContext } from '../record'

export const GLOBE_CANVAS = '.globe-container canvas'
export const MAPBOX_CANVAS = '.mapbox-globe-container canvas'
export const JPEG_QUALITY = 0.92
/** Longest wait for an animation frame before the take fails (display asleep or session locked). */
export const NO_FRAME_MS = 30_000
const JPEG_PREFIX = 'data:image/jpeg;base64,'
/** Tile polls per frame before the grab gives up (25 ms each: 10 s). */
const MAX_TILE_POLLS = 400

/** Name of frame `index` (0-based); ffmpeg reads the sequence as f%06d.jpg. */
export function frameName(index: number): string {
  if (!Number.isInteger(index) || index < 0) throw new Error(`frame index ${index} is not a non-negative integer`)
  return `f${String(index).padStart(6, '0')}.jpg`
}

/** Frame index a take reaches at `seconds` (rounded to the nearest frame). */
export function frameCount(seconds: number, fps: number): number {
  if (!(seconds > 0) || !(fps > 0)) throw new Error(`cannot count frames of ${seconds} s at ${fps} fps`)
  return Math.round(seconds * fps)
}

/** Page-side: resolves after two animation frames, rejects after NO_FRAME_MS without one. */
const TWO_FRAMES = `new Promise(function(resolve, reject) {
  var timer = setTimeout(function() {
    reject(new Error('no animation frame for ${NO_FRAME_MS / 1000} s: headed Chrome draws only on an awake, unlocked Windows display'));
  }, ${NO_FRAME_MS});
  requestAnimationFrame(function() { requestAnimationFrame(function() { clearTimeout(timer); resolve(); }); });
})`

/** Let the page draw twice (bounded): the studio scenes' settle after a state change. */
export async function nextFrames(page: Page): Promise<void> {
  await page.evaluate(TWO_FRAMES)
}

/** Page-side: the WebGL renderer string (UNMASKED_RENDERER_WEBGL) of a fresh context. */
const RENDERER = `(function() {
  var canvas = document.createElement('canvas');
  var gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
  if (!gl) return '';
  var info = gl.getExtension('WEBGL_debug_renderer_info');
  return info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : '';
})()`

/** Write {"renderer": ...} for globe.py, which refuses anything but the NVIDIA (spec 4.11). */
export async function writeRenderer(page: Page, path: string): Promise<void> {
  const renderer = (await page.evaluate(RENDERER)) as string
  writeFileSync(path, JSON.stringify({ renderer }))
  console.log(`  gpu: ${renderer}`)
}

/** Page-side code of one frame: advance the synthetic clock, wait for the draw (and tiles), read the canvas. */
function grabSource(canvasSelector: string, waitForTiles: boolean): string {
  return `(async function() {
    var canvas = document.querySelector(${JSON.stringify(canvasSelector)});
    if (!canvas) throw new Error('no canvas matches ' + ${JSON.stringify(canvasSelector)});
    window.__tickFrame();
    await ${TWO_FRAMES};
    if (${waitForTiles}) {
      var polls = 0;
      while (!window.__DEMO.mapboxTilesLoaded()) {
        if (++polls > ${MAX_TILE_POLLS}) throw new Error('Mapbox tiles did not load within 10 s for this frame');
        await new Promise(function(r) { setTimeout(r, 25); });
      }
      if (polls > 0) await ${TWO_FRAMES};
    }
    return canvas.toDataURL('image/jpeg', ${JPEG_QUALITY});
  })()`
}

/** Per-frame work around a grab: `before` sets the pose of frame `index`, `after` reads the page in it. */
export type FrameHooks = { before?: (index: number) => Promise<void>; after?: (index: number) => Promise<void> }

/** Writes the consecutive frames of one take into `dir`, which must be empty. */
export class FrameGrabber {
  private next = 0

  constructor(
    private readonly dir: string,
    private readonly canvasSelector: string,
    private readonly waitForTiles: boolean,
  ) {
    mkdirSync(dir, { recursive: true })
    if (readdirSync(dir).length > 0) throw new Error(`frames directory ${dir} is not empty`)
  }

  /** Frames grabbed so far. */
  get frames(): number {
    return this.next
  }

  /**
   * Grab frames until the take reaches `untilSeconds` (frame index round(untilSeconds * fps));
   * the page animates on the synthetic clock meanwhile. Cumulative targets keep the
   * rounding of consecutive segments from adding up. `hooks.before` runs before each grab
   * (a sweep sets its camera pose there), `hooks.after` after it (a PointTracker samples there).
   */
  async grabUntil(ctx: SceneContext, untilSeconds: number, hooks: FrameHooks = {}): Promise<void> {
    const target = frameCount(untilSeconds, ctx.fps)
    if (target <= this.next) throw new Error(`the take is already at frame ${this.next}; nothing to grab until ${untilSeconds} s`)
    const code = grabSource(this.canvasSelector, this.waitForTiles)
    while (this.next < target) {
      if (hooks.before) await hooks.before(this.next)
      const url = (await ctx.page.evaluate(code)) as string
      if (!url.startsWith(JPEG_PREFIX)) throw new Error(`canvas ${this.canvasSelector} returned ${url.slice(0, 32)}, not a JPEG`)
      writeFileSync(join(this.dir, frameName(this.next)), Buffer.from(url.slice(JPEG_PREFIX.length), 'base64'))
      if (hooks.after) await hooks.after(this.next)
      this.next++
    }
    console.log(`  frames: ${this.next}`)
  }
}

export type TrackedPlace = { id: string; lat: number; lng: number }

/**
 * Where the page draws each place in every grabbed frame (owner rule: globe markers are
 * projected per frame from their coordinates). sample() reads window.__DEMO.screenPoint
 * for all places in one page call right after a grab; write() stores points.json,
 * {place id: [[x, y] | null, ...]} with exactly one entry per frame, which
 * pipeline/studio/capture/globe.py turns into the place events' tracks.
 */
export class PointTracker {
  private readonly tracks: Record<string, ([number, number] | null)[]> = {}
  private readonly code: string

  constructor(private readonly places: readonly TrackedPlace[]) {
    for (const place of places) this.tracks[place.id] = []
    const coords = JSON.stringify(places.map((p) => [p.lat, p.lng]))
    this.code = `(${coords}).map(function(p) { return window.__DEMO.screenPoint(p[0], p[1]); })`
  }

  async sample(page: Page): Promise<void> {
    const points = (await page.evaluate(this.code)) as (ScreenPoint | null)[]
    this.places.forEach((place, i) => {
      const point = points[i]
      this.tracks[place.id].push(point === null ? null : [point.x, point.y])
    })
  }

  write(path: string, frames: number): void {
    for (const [id, track] of Object.entries(this.tracks)) {
      if (track.length !== frames) throw new Error(`place ${id}: ${track.length} points for ${frames} frames`)
    }
    writeFileSync(path, JSON.stringify(this.tracks))
  }
}
```

**`ancient-nerds-map/video/scenes/studio-globe.ts`** (complete file):

```ts
/**
 * Studio globe scenes, landscape 1920x1080 (spec 2026-09-26 section 4.5), driven by
 * pipeline/studio/capture/globe.py through STUDIO_SCENE_INPUT (record.ts sets it
 * from --input). Our vector globe only: every distance stays at or above 1.2,
 * well outside CAMERA_EXTENDED.MAPBOX_ENABLE_DISTANCE (1.12), so no Mapbox tile
 * is drawn and the shot carries no map credit. Frames are grabbed one by one
 * (studio-frames.ts) into the input's frames_dir; every scene first writes the
 * page's WebGL renderer to renderer_path, which globe.py checks (spec 4.11).
 * Places are projected per frame (owner rule): after every grabbed frame a
 * PointTracker reads where the page draws each place (window.__DEMO.screenPoint)
 * and points_path receives one pixel or null per frame and place.
 *
 *   studio-globe-flyto   space pose, rotate onto lat/lng (rotate_s), zoom to
 *                        `distance` (zoom_s), hold; optional empire layer; with
 *                        `places` (the target) it tracks the target in every frame
 *   studio-globe-places  a pose that frames the places, fixed (sweep_lng_deg 0:
 *                        computed in Python by projection.fit_globe_distance) or
 *                        sweeping the camera longitude from cam_lng by
 *                        sweep_lng_deg over the take (globe.py's world
 *                        distribution is a sweep of 360 degrees)
 *
 *   VITE_DEV_API_TARGET=https://ancientnerds.com npm run video:record -- \
 *     studio-globe-flyto --fps 60 --input <input.json> --out <dir>
 */

import { readFileSync } from 'fs'
import type { SceneContext, SceneDefinition } from '../record'
import { FrameGrabber, GLOBE_CANVAS, PointTracker, type TrackedPlace, nextFrames, writeRenderer } from './studio-frames.js'

export interface StudioInput {
  scene: string
  duration_s: number
  frames_dir: string
  /** Where the scene writes {"renderer": <WebGL renderer>} (studio-frames.ts writeRenderer). */
  renderer_path: string
}

export interface FlytoInput extends StudioInput {
  scene: 'flyto'
  lat: number
  lng: number
  distance: number
  empire: string | null
  rotate_s: number
  zoom_s: number
  /** With a place: the target to track in every frame, and where its pixels go. */
  places?: TrackedPlace[]
  points_path?: string
}

export interface PlacesInput extends StudioInput {
  scene: 'places'
  cam_lat: number
  /** Camera longitude of the first frame. */
  cam_lng: number
  distance: number
  /** Degrees the camera longitude turns over the take (0: a fixed pose). */
  sweep_lng_deg: number
  places: TrackedPlace[]
  /** Where the scene writes {place id: [[x, y] | null, ...]}, one entry per frame. */
  points_path: string
}

/** Three.js camera distance the fly-to starts from: the whole globe in frame. */
export const SPACE_DISTANCE = 2.3
/** Start this far west and north of the target so the first second visibly rotates. */
export const START_LNG_OFFSET = -40
export const START_LAT_OFFSET = 15

/** Read the scene input written by globe.py; the scene must match and both output paths must be named. */
export function readStudioInput<T extends StudioInput>(scene: T['scene']): T {
  const path = process.env.STUDIO_SCENE_INPUT
  if (!path) throw new Error('STUDIO_SCENE_INPUT not set: pass --input <input.json>')
  const input = JSON.parse(readFileSync(path, 'utf-8')) as T
  if (input.scene !== scene) throw new Error(`${path} holds a ${input.scene} input, the scene needs ${scene}`)
  if (!(input.duration_s > 0)) throw new Error(`${path}: duration_s must be positive`)
  if (typeof input.frames_dir !== 'string' || input.frames_dir === '') throw new Error(`${path}: frames_dir is missing`)
  if (typeof input.renderer_path !== 'string' || input.renderer_path === '') throw new Error(`${path}: renderer_path is missing`)
  return input
}

/** Start pose of the fly-to (latitude clamped away from the poles, where lookAt degenerates). */
export function flytoStart(input: Pick<FlytoInput, 'lat' | 'lng'>): { lng: number; lat: number } {
  return { lng: input.lng + START_LNG_OFFSET, lat: Math.max(-70, Math.min(70, input.lat + START_LAT_OFFSET)) }
}

/** Camera longitude of frame `index` of a sweep: linear from `from` by `sweep` degrees over the take, in -180..180. */
export function sweepLng(from: number, sweep: number, index: number, fps: number, durationS: number): number {
  const lng = from + (sweep * index) / (fps * durationS)
  return ((((lng + 180) % 360) + 360) % 360) - 180
}

async function runFlyto(ctx: SceneContext): Promise<void> {
  const input = readStudioInput<FlytoInput>('flyto')
  const { page, demo, fire } = ctx
  if (input.places !== undefined && !input.points_path) throw new Error('a flyto input with places needs points_path')
  const grabber = new FrameGrabber(input.frames_dir, GLOBE_CANVAS, false)
  await writeRenderer(page, input.renderer_path)
  const tracker = input.places === undefined ? null : new PointTracker(input.places)
  const hooks = tracker ? { after: () => tracker.sample(page) } : {}
  const start = flytoStart(input)
  await demo.setAutoRotate(false)
  await demo.setCameraPose(start.lng, start.lat, SPACE_DISTANCE)
  if (input.empire) await demo.showEmpire(input.empire)
  await demo.setFlyToDuration(input.rotate_s * 1000)
  await nextFrames(page)
  // The app's fly-to keeps the distance it starts with, so rotate first, then zoom.
  fire(`window.__DEMO.flyTo(${input.lng}, ${input.lat})`)
  await grabber.grabUntil(ctx, input.rotate_s, hooks)
  fire(`window.__DEMO.smoothZoom(${SPACE_DISTANCE}, ${input.distance}, ${input.zoom_s * 1000})`)
  await grabber.grabUntil(ctx, input.rotate_s + input.zoom_s, hooks)
  await grabber.grabUntil(ctx, input.duration_s, hooks)
  if (tracker && input.points_path) tracker.write(input.points_path, grabber.frames)
}

async function runPlaces(ctx: SceneContext): Promise<void> {
  const input = readStudioInput<PlacesInput>('places')
  const { page, demo } = ctx
  const grabber = new FrameGrabber(input.frames_dir, GLOBE_CANVAS, false)
  await writeRenderer(page, input.renderer_path)
  await demo.setAutoRotate(false)
  await demo.setCameraPose(input.cam_lng, input.cam_lat, input.distance)
  await nextFrames(page)
  // The page's own camera (telephoto FOV included) says where each place is drawn, frame by frame.
  const tracker = new PointTracker(input.places)
  const turn = async (index: number) => {
    await demo.setCameraPose(sweepLng(input.cam_lng, input.sweep_lng_deg, index, ctx.fps, input.duration_s), input.cam_lat, input.distance)
  }
  await grabber.grabUntil(ctx, input.duration_s, {
    ...(input.sweep_lng_deg === 0 ? {} : { before: turn }),
    after: () => tracker.sample(page),
  })
  tracker.write(input.points_path, grabber.frames)
}

export const studioGlobeScenes: SceneDefinition[] = [
  { name: 'studio-globe-flyto', duration: () => readStudioInput<FlytoInput>('flyto').duration_s, resolution: 'section', grabsFrames: true, run: runFlyto },
  { name: 'studio-globe-places', duration: () => readStudioInput<PlacesInput>('places').duration_s, resolution: 'section', grabsFrames: true, run: runPlaces },
]
```

**`ancient-nerds-map/video/scenes/studio-mapbox.ts`** (complete file):

```ts
/**
 * Studio Mapbox scenes, landscape 1920x1080 (spec 2026-09-26 section 4.5): the
 * site-short fly-in adapted to 16:9 and a plain orbit. Same recording look and
 * tile warm-up as the shorts (prepareMapbox / warmPath from site-short.ts);
 * input from pipeline/studio/capture/globe.py via STUDIO_SCENE_INPUT; every
 * frame is grabbed exactly (studio-frames.ts), each after its tiles loaded;
 * the page's WebGL renderer goes to renderer_path first (spec 4.11).
 *
 *   studio-mapbox-flyin  satellite globe from space, rotate onto the site
 *                        (ROTATE_S), zoom in with tilt (ZOOM_S), orbit for the rest
 *   studio-mapbox-orbit  terrain orbit around the site, bearing_from to bearing_to
 *
 * Map content: the capture manifest credits "© Mapbox © OpenStreetMap © Maxar".
 */

import { getCountryCode } from '../../src/utils/countryFlags'
import type { MapboxKeyframe } from '../../src/utils/demoApi'
import type { SceneContext, SceneDefinition } from '../record'
import { TERRAIN_EXAGGERATION, prepareMapbox, warmPath } from './site-short.js'
import { FrameGrabber, MAPBOX_CANVAS, writeRenderer } from './studio-frames.js'
import { type StudioInput, flytoStart, readStudioInput } from './studio-globe.js'

export interface FlyinInput extends StudioInput {
  scene: 'mapbox_flyin'
  name: string
  lat: number
  lng: number
  country?: string
  orbit_zoom: number
}

export interface OrbitInput extends StudioInput {
  scene: 'mapbox_orbit'
  name: string
  lat: number
  lng: number
  country?: string
  zoom: number
  pitch: number
  bearing_from: number
  bearing_to: number
}

/**
 * The satellite globe's diameter is about 512 * 2^zoom / pi px: z2.4 fills ~80 % of
 * the 1080 px frame height (z1.7 filled half of it in the first real take, 2026-09-26).
 */
export const SPACE_ZOOM = 2.4
export const ROTATE_S = 1.2
export const ZOOM_S = 2.4
export const ORBIT_PITCH = 60
export const ORBIT_BEARING_FROM = 20
export const ORBIT_BEARING_TO = 100

/** Space pose, rotate onto the site, zoom in with tilt, orbit until the end of the take. */
export function flyinPath(input: Pick<FlyinInput, 'lat' | 'lng' | 'orbit_zoom' | 'duration_s'>): MapboxKeyframe[] {
  const minimum = ROTATE_S + ZOOM_S + 1
  if (input.duration_s < minimum) throw new Error(`studio-mapbox-flyin needs at least ${minimum} s, got ${input.duration_s}`)
  const t = (s: number) => s / input.duration_s
  const here = { lng: input.lng, lat: input.lat }
  return [
    { at: 0, ...flytoStart(input), zoom: SPACE_ZOOM, pitch: 0, bearing: 0, terrain: null },
    { at: t(ROTATE_S), ...here, zoom: SPACE_ZOOM, pitch: 0, bearing: 0, terrain: TERRAIN_EXAGGERATION },
    { at: t(ROTATE_S + ZOOM_S), ...here, zoom: input.orbit_zoom, pitch: ORBIT_PITCH, bearing: ORBIT_BEARING_FROM },
    { at: 1, ...here, zoom: input.orbit_zoom, pitch: ORBIT_PITCH, bearing: ORBIT_BEARING_TO },
  ]
}

/** One eased sweep of the bearing around the site. */
export function orbitPath(input: Pick<OrbitInput, 'lat' | 'lng' | 'zoom' | 'pitch' | 'bearing_from' | 'bearing_to'>): MapboxKeyframe[] {
  const pose = { lng: input.lng, lat: input.lat, zoom: input.zoom, pitch: input.pitch }
  return [
    { at: 0, ...pose, bearing: input.bearing_from, terrain: TERRAIN_EXAGGERATION },
    { at: 1, ...pose, bearing: input.bearing_to },
  ]
}

/**
 * A studio take's `country` is shown data (plan C binds it to the site export): a
 * name the site's country table does not know would make prepareMapbox log "no
 * highlight" and record the take without it, so it is refused before anything
 * is recorded. The site Shorts keep prepareMapbox's own behaviour.
 */
export function checkCountry(country: string | undefined): void {
  if (country !== undefined && getCountryCode(country) === null) throw new Error(`unknown country ${JSON.stringify(country)}: getCountryCode has no code for it, the take would lack its highlight`)
}

async function flyPath(ctx: SceneContext, input: FlyinInput | OrbitInput, path: MapboxKeyframe[]): Promise<void> {
  checkCountry(input.country)
  const grabber = new FrameGrabber(input.frames_dir, MAPBOX_CANVAS, true)
  await writeRenderer(ctx.page, input.renderer_path)
  await prepareMapbox(ctx, input)
  await warmPath(ctx, path, input.duration_s)
  ctx.fire(`window.__DEMO.mapboxPath(${JSON.stringify(path)}, ${input.duration_s * 1000})`)
  await grabber.grabUntil(ctx, input.duration_s)
}

async function runFlyin(ctx: SceneContext): Promise<void> {
  const input = readStudioInput<FlyinInput>('mapbox_flyin')
  await flyPath(ctx, input, flyinPath(input))
}

async function runOrbit(ctx: SceneContext): Promise<void> {
  const input = readStudioInput<OrbitInput>('mapbox_orbit')
  await flyPath(ctx, input, orbitPath(input))
}

export const studioMapboxScenes: SceneDefinition[] = [
  { name: 'studio-mapbox-flyin', duration: () => readStudioInput<FlyinInput>('mapbox_flyin').duration_s, resolution: 'section', grabsFrames: true, run: runFlyin },
  { name: 'studio-mapbox-orbit', duration: () => readStudioInput<OrbitInput>('mapbox_orbit').duration_s, resolution: 'section', grabsFrames: true, run: runOrbit },
]
```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
import { siteShortScenes } from './scenes/site-short.js'
```

with:

```ts
import { siteShortScenes } from './scenes/site-short.js'
import { studioGlobeScenes } from './scenes/studio-globe.js'
import { studioMapboxScenes } from './scenes/studio-mapbox.js'
```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
  waitForTiles?: boolean
  run: (ctx: SceneContext) => Promise<void>
}
```

with:

```ts
  waitForTiles?: boolean
  /**
   * The scene writes its own exact frames (scenes/studio-frames.ts) instead of the
   * MediaRecorder stream: no WebM and no encode step here (studio captures).
   */
  grabsFrames?: boolean
  run: (ctx: SceneContext) => Promise<void>
}
```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
  ...siteShortScenes,
]
```

with:

```ts
  ...siteShortScenes,
  ...studioGlobeScenes,
  ...studioMapboxScenes,
]
```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
 *   --input <path>    site.json for the site-short scenes (exposed as SITE_SHORT_INPUT)
```

with:

```ts
 *   --input <path>    site.json for the site-short scenes (exposed as SITE_SHORT_INPUT) or the
 *                     studio scene input of pipeline/studio/capture/globe.py (STUDIO_SCENE_INPUT)
```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
  if (args.input) process.env.SITE_SHORT_INPUT = args.input
```

with:

```ts
  if (args.input) {
    process.env.SITE_SHORT_INPUT = args.input
    process.env.STUDIO_SCENE_INPUT = args.input
  }
```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
      if (target.input) process.env.SITE_SHORT_INPUT = target.input
```

with:

```ts
      if (target.input) {
        process.env.SITE_SHORT_INPUT = target.input
        process.env.STUDIO_SCENE_INPUT = target.input
      }
```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
        await scene.run(ctx)

```

with:

```ts
        await scene.run(ctx)
        if (scene.grabsFrames) continue

```

In `ancient-nerds-map/video/record.ts`, replace:

```ts
  const vite = spawn('npm', ['run', 'dev', '--', '--port', String(DEV_SERVER_PORT)], {
```

with:

```ts
  // --strictPort: a dev server left running on the port (an interrupted take) must fail this
  // start, not silently serve the page from an older checkout while Vite moves to the next port
  const vite = spawn('npm', ['run', 'dev', '--', '--port', String(DEV_SERVER_PORT), '--strictPort'], {
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ancient-nerds-map && npx vitest run video/scenes/__tests__/studio-scenes.test.ts && npx tsc -p video/tsconfig.json --noEmit`
Expected: `Tests  12 passed (12)`, then no tsc output.

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/video/scenes/studio-frames.ts ancient-nerds-map/video/scenes/studio-globe.ts ancient-nerds-map/video/scenes/studio-mapbox.ts ancient-nerds-map/video/scenes/__tests__/studio-scenes.test.ts ancient-nerds-map/video/scenes/site-short.ts ancient-nerds-map/video/record.ts
git commit -m "Add the recorder's landscape studio scenes that grab every frame exactly and record their GPU" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 36: Real captures on the workstation (local, not CI)

No new files. One capture of each kind against the real site, the real globe and the real APIs, proving the GPU rule end to end, plus every platform moment the owner named (search, result, fly-to, zoom into Mapbox, Measure 0.9 km, Empire Borders, Proximity, details page), a fly-to with the Roman empire layer, a sweeping places take whose pins must follow the globe, and a world distribution. Needs Tasks 23-35, plan C's Task 1, the frontend's `node_modules` and an **awake, unlocked Windows display** for the whole run (headed Chrome draws only then; measured 2026-09-26: with the display throttled the frame-by-frame globe takes crawled, a 5-second take in 7 minutes, and with the display asleep the first frame never came). The Mapbox token comes from the main checkout's `.env` the way plan C's `config.load_env` reads it; nothing prints it.

- [ ] **Step 1: Write the driver into a scratch episode**

```bash
S="$(cygpath -m "$TMP")/studio-real" && rm -rf "$S" && mkdir -p "$S/ep/captures" && echo "$S"
```

Create `$S/drive.py` (the directory printed above) with exactly this content:

```python
"""Real captures through pipeline.studio.capture (Task 36); prints manifests, never the token."""

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from pipeline.studio import capture

load_dotenv(Path("C:/PythonProjects/AncientMap/.env"), override=False)
EP = Path(sys.argv[1])
SPECS = {
    "topdown": {"id": "td1", "kind": "mapbox_topdown", "center": {"lat": 34.0029, "lng": 36.2018},
                "zoom": 15.0, "bearing": 0, "style": "satellite-v9", "width": 1280, "height": 720,
                "pins": [{"id": "p2", "label": "Quarry", "lat": 33.99917, "lng": 36.20028},
                         {"id": "p1", "label": "Temple of Jupiter", "lat": 34.00667, "lng": 36.20333}]},
    "source": {"id": "src1", "kind": "source", "url": "https://en.wikipedia.org/wiki/Baalbek",
               "quote": "from the three massive stones in its foundation"},
    "flyto": {"id": "g1", "kind": "globe", "scene": "flyto", "lat": 34.0067, "lng": 36.2033,
              "distance": 1.35, "empire": None, "rotate_s": 1.5, "zoom_s": 2.0, "duration_s": 5,
              "place": {"id": "p1", "label": "Baalbek"}},
    "places": {"id": "g2", "kind": "globe", "scene": "places", "lead_s": 0.8, "interval_s": 0.6,
               "duration_s": 4,
               "places": [{"id": "p2", "label": "Giza", "lat": 29.9792, "lng": 31.1342},
                          {"id": "p3", "label": "Athens", "lat": 37.9715, "lng": 23.7257},
                          {"id": "p1", "label": "Baalbek", "lat": 34.0067, "lng": 36.2033},
                          {"id": "p4", "label": "Rome", "lat": 41.8902, "lng": 12.4922}]},
    "flyin": {"id": "m1", "kind": "globe", "scene": "mapbox_flyin", "name": "Baalbek",
              "lat": 34.0067, "lng": 36.2033, "country": "Lebanon", "orbit_zoom": 15.5,
              "duration_s": 5},
    "orbit": {"id": "m2", "kind": "globe", "scene": "mapbox_orbit", "name": "Baalbek",
              "lat": 34.0067, "lng": 36.2033, "country": "Lebanon", "zoom": 16.5, "pitch": 60,
              "bearing_from": 20, "bearing_to": 80, "duration_s": 3},
    "platform": {"id": "platform-01", "kind": "platform", "target": "local", "hud": 1.3,
                 "actions": [{"do": "pause_rotation"}, {"do": "search", "q": "baalbek"},
                             {"do": "click_result", "title": "Baalbek Stones"},
                             {"do": "fly_wait", "s": 4.0}, {"do": "wait", "s": 1.0}]},
    # the owner's platform moments: zoom into Mapbox, Measure 0.9 km (quarry to temple),
    # Empire Borders, Proximity, the details page
    "platform2": {"id": "platform-02", "kind": "platform", "target": "local", "hud": 1.3,
                  "actions": [{"do": "pause_rotation"}, {"do": "search", "q": "baalbek"},
                              {"do": "click_result", "title": "Baalbek Stones"},
                              {"do": "fly_wait", "s": 3.0}, {"do": "zoom", "to": 90},
                              {"do": "measure", "a": {"lat": 33.99917, "lng": 36.20028},
                               "b": {"lat": 34.00667, "lng": 36.20333}},
                              {"do": "wait", "s": 1.5},
                              {"do": "toggle_layer", "label": "Empire Borders"}, {"do": "wait", "s": 1.0},
                              {"do": "proximity", "at": {"lat": 34.0067, "lng": 36.2033}},
                              {"do": "wait", "s": 1.0},
                              {"do": "open_details", "title": "Baalbek Stones"}, {"do": "wait", "s": 1.5}]},
    # g1 with the Roman empire layer (a valid id, empires.generated.json)
    "flyto_empire": {"id": "g1e", "kind": "globe", "scene": "flyto", "lat": 34.0067, "lng": 36.2033,
                     "distance": 1.35, "empire": "roman", "rotate_s": 1.5, "zoom_s": 2.0,
                     "duration_s": 5, "place": {"id": "p1", "label": "Baalbek"}},
    # places 111 degrees of longitude apart: the camera sweeps east and every pin must follow it
    "sweep": {"id": "g3", "kind": "globe", "scene": "places", "lead_s": 0.5, "interval_s": 1.0,
              "duration_s": 8, "sweep_lng_deg": 150, "cam_lat": 35, "cam_lng_from": -30,
              "distance": 2.2,
              "places": [{"id": "s1", "label": "Stonehenge", "lat": 51.1789, "lng": -1.8262},
                         {"id": "s2", "label": "Göbekli Tepe", "lat": 37.2231, "lng": 38.9224},
                         {"id": "s3", "label": "Mohenjo-daro", "lat": 27.3294, "lng": 68.1386},
                         {"id": "s4", "label": "Terracotta Army", "lat": 34.3853, "lng": 109.2785}]},
    # a world distribution: one turn of the whole globe, three places labelled, the rest dots
    # (in an episode, plan C resolves the dots from site ids into unlabelled places like these)
    "distribution": {"id": "g4", "kind": "globe", "scene": "distribution", "duration_s": 16,
                     "places": [{"id": "w1", "label": "Giza", "lat": 29.9792, "lng": 31.1342},
                                {"id": "w2", "label": "Stonehenge", "lat": 51.1789, "lng": -1.8262},
                                {"id": "w3", "label": "Teotihuacan", "lat": 19.6925, "lng": -98.8438},
                                {"id": "w4", "lat": 37.2231, "lng": 38.9224},
                                {"id": "w5", "lat": 27.3294, "lng": 68.1386},
                                {"id": "w6", "lat": 34.3853, "lng": 109.2785},
                                {"id": "w7", "lat": -10.8933, "lng": -77.5200},
                                {"id": "w8", "lat": 6.8442, "lng": 158.3358}]},
}
FUNCTIONS = {"globe": capture.record_globe, "mapbox_topdown": capture.mapbox_topdown,
             "source": capture.capture_source, "platform": capture.record_platform}
for name in sys.argv[2:]:
    spec = SPECS[name]
    started = time.time()
    manifest = FUNCTIONS[spec["kind"]](EP, spec)
    (EP / "captures" / f"{spec['id']}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    keys = ("id", "kind", "path", "fps", "duration_s", "width", "height", "credits")
    print(name, f"{time.time() - started:.0f}s", json.dumps({k: manifest[k] for k in keys}), flush=True)
    print("  events:", [e["name"] for e in manifest["events"]], flush=True)
    for e in manifest["events"]:
        if "track" in e:
            shown = sum(p is not None for p in e["track"])
            print(f"  place {e['target']} at {e['t']} s: {shown} of {len(e['track'])} frames shown,"
                  f" first {e['track'][0]}, last {next(p for p in reversed(e['track']) if p)}", flush=True)
```

- [ ] **Step 2: Run the fast captures, then the globe and Mapbox takes**

```bash
S="$(cygpath -m "$TMP")/studio-real"
PYTHONPATH="$(pwd -W)" ./.venv/Scripts/python.exe "$S/drive.py" "$S/ep" topdown source platform platform2 flyto places
PYTHONPATH="$(pwd -W)" ./.venv/Scripts/python.exe "$S/drive.py" "$S/ep" flyto_empire sweep distribution
PYTHONPATH="$(pwd -W)" ./.venv/Scripts/python.exe "$S/drive.py" "$S/ep" flyin orbit
```

Expected: `topdown` a still `2560x1440` with two `pin` events and `© Mapbox © Maxar` (3 s); `source` a still `2560x3686` (the height follows the page, read from the PNG) with the events `gpu`, `page`, `highlight` (9 s); `platform` a 60 fps clip at the display's pixel size (`2880x1620` on the workstation, about 9.5 s) with the events `gpu`, `pause_rotation`, `search`, `click_result`, `fly_wait`, `wait` and the credit `© Mapbox © OpenStreetMap © Maxar` (28 s); `platform2` the same kind of clip with the events, in this order, `gpu`, `pause_rotation`, `search`, `click_result`, `fly_wait`, `zoom`, `measure`, `measure_a`, `measure_b`, `wait`, `expand_layers` (only when the layer panel was minimized), `toggle_layer`, `wait`, `proximity`, `proximity_center`, `wait`, `open_details`, `wait`; `flyto`, `flyto_empire` and `places` 60 fps `1920x1080` clips of 5.0, 5.0 and 4.0 s, the fly-tos with `rotate`, `zoom`, `arrive` and the `place` event of Baalbek at 3.5 s (its track 90 frames, all shown), `places` with one `place` event per place, no credits; `sweep` an 8.0 s clip whose four `place` events carry tracks that move from frame to frame (first and last pixel differ) and are null where a place has turned out of the label band; `distribution` a 16.0 s clip with eight `place` events, three with labels, each at the first frame its place faces the camera; `flyin` and `orbit` clips with the Mapbox credit. Every browser capture's first event is `{"t": 0.0, "name": "gpu", "label": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)"}`. The globe and Mapbox takes grab frame by frame: measured 2026-09-26 with the display throttled, `flyto` took 428 s, `places` 385 s, `flyin` 1138 s (a tile wait on every frame) and `orbit` 456 s.

- [ ] **Step 3: Look at them**

```bash
S="$(cygpath -m "$TMP")/studio-real/ep/captures"
for f in g1 g1e g2 g3 g4 m1 m2 platform-01 platform-02; do ffprobe -v error -show_entries stream=codec_name,codec_tag_string,width,height,r_frame_rate,nb_frames,color_space -of compact "$S/$f.mp4"; ffmpeg -hide_banner -loglevel error -y -i "$S/$f.mp4" -vf "select='not(mod(n\,50))',scale=480:-1,tile=3x2" -frames:v 1 "$S/$f-sheet.jpg"; done
ffmpeg -hide_banner -loglevel error -y -i "$S/platform-02.mp4" -vf "select='not(mod(n\,30))',scale=640:-1,tile=4x4" -frames:v 1 "$S/platform-02-moments.jpg"
```

Expected: every clip `codec_name=hevc|codec_tag_string=hvc1|...|r_frame_rate=60/1|...|color_space=bt709`. Open the sheets: `g1` rotates onto the Levant and zooms in (our vector globe, no satellite imagery); `g1e` the same with the Roman empire's borders drawn on the globe; `g2` a fixed pose over the eastern Mediterranean; `g3` the globe turning east from Britain to China; `g4` one full turn of the whole globe; `m1` the satellite globe filling most of the frame height, then the dive to Baalbek; `platform-01` the site without panels, the NERV cursor, the search result and the fly-to. Open `platform-02-moments.jpg` and find each moment: the zoom into the Mapbox view with the selected site's label still shown, the measure line from the quarry to the temple with its label of about 0.9 km, the Empire Borders layer switched on, the proximity circle with its result list, and the site popup of the details page. Open `td1.jpg` (the quarry pin in the south-west, the temple pin north-east of it) and `src1.png` (the quote outlined in green).

- [ ] **Step 4: Record the result**

Note in the task report, for every take, its wall time, size, duration and event names (the driver prints them), and for `platform-02` which of the five moments looked right on the sheet. A moment that did not work is a defect of Task 30 or 33 to fix and re-take, never a skipped check.

- [ ] **Step 5: Clean up**

```bash
rm -rf "$(cygpath -m "$TMP")/studio-real"
```

No commit.

### Task 37: The cross-plan contract test and whole-stream verification

**Files:**
- Test: `video/test/contract.test.ts`

Check C21 must print its path first. Plan C's Task 21 commits `tests/pipeline/studio/golden_timeline.json`, its compiler's output for its fixture episode, and its `test_golden_timeline_is_current` keeps the file equal to what the compiler writes. This task adds the renderer's side of that contract: the same file must parse, pass every `checkBlocks` rule, run at 60 fps and keep its hook captions uppercase. A later drift on either side (a renamed key, a changed caption, credit or ticker shape, a new prop in plan C's `resolve_refs`, a new required key in `parseTimeline`) then fails a suite instead of the first real `episode render`. The test reads the file where plan C commits it, never a copy. Then every gate that covers this stream's files.

- [ ] **Step 1: Write the contract test**

**`video/test/contract.test.ts`** (complete file):

```ts
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { checkBlocks } from '../src/blocks'
import { parseTimeline } from '../src/timeline'

/**
 * Plan C's compiler output for its fixture episode (plan C Task 21, kept current by its
 * test_golden_timeline_is_current): the renderer must read it exactly as committed.
 */
const GOLDEN = new URL('../../tests/pipeline/studio/golden_timeline.json', import.meta.url)

describe("plan C's compiled timeline.json (contracts C8 and D3)", () => {
  it('parses, passes every block check, runs at 60 fps and keeps its hook captions uppercase', () => {
    const raw: unknown = JSON.parse(readFileSync(GOLDEN, 'utf-8'))
    expect(() => checkBlocks(parseTimeline(raw))).not.toThrow()
    const timeline = parseTimeline(raw)
    expect(timeline.fps).toBe(60)
    for (const caption of timeline.captions) expect(caption.text).toBe(caption.text.toUpperCase())
  })
})
```

- [ ] **Step 2: Run it**

Run: `cd video && npx vitest run test/contract.test.ts`
Expected: `Tests  1 passed (1)`. Both sides already exist, so this test passes at once; it exists to fail on a later drift. If it fails now, its message names the defect: fix the side that is wrong (plan C's compiler, then regenerate the golden file with the command of plan C Task 21 Step 4, or this plan's parser), never the golden file by hand.

- [ ] **Step 3: Commit**

```bash
git add video/test/contract.test.ts
git commit -m "Check that the renderer reads plan C's compiled golden timeline as committed" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Renderer**

```bash
cd video && npx tsc --noEmit && npx vitest run
```

Expected: no tsc output; `Test Files  25 passed (25)`, `Tests  204 passed (204)` (Task 21's 24 files and 203 tests plus the contract test).

- [ ] **Step 5: Captures and the backend suite**

```bash
./.venv/Scripts/python.exe -m pytest tests/pipeline/studio/capture -m "not integration and not live_llm" -q -rs
./.venv/Scripts/python.exe -m ruff check api/ pipeline/ && ./.venv/Scripts/python.exe -m ruff format --check pipeline/studio/capture tests/pipeline/studio/capture
./.venv/Scripts/python.exe -m vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80
./.venv/Scripts/lint-imports.exe
./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"
```

Expected: `142 passed, 1 skipped` for the capture suite on the workstation; ruff and vulture clean; `Contracts: 2 kept, 0 broken.`; the backend suite green with the capture tests included (compare with the count before Task 23: +143 collected).

- [ ] **Step 6: Frontend and recorder**

```bash
cd ancient-nerds-map && npm run type-check && npx tsc -p video/tsconfig.json --noEmit && npm run test && npx knip --no-progress --include files,dependencies,devDependencies
```

Expected: both type checks clean, every vitest file passes (the new `videoMode`, `screenPoint` and `studio-scenes` tests included), knip reports nothing.

- [ ] **Step 7: The local runs**

Task 22 (smoke render) and Task 36 (real captures) are the local end-to-end proof; run them once more if anything in `video/` or `pipeline/studio/capture/` changed after they last ran.

No further commit (Steps 4-7 change nothing). Report the counts and any gate that could not run on this machine instead of claiming it passed (CLAUDE.md "Local verification").

---

## Spec coverage (self-review)

| Spec | Where |
|---|---|
| 4.5 platform takes: Playwright Chrome, CDP screencast 1920x1080 at device scale 2, local or production, declarative actions (plus `zoom`, `proximity`, `filter` for the owner's moments), fast cursor (0.25 s against a deadline, 45 ms), NERV cursor via `?video=1`, CFR 60 fps, action times as events, no analytics visit | Task 30 (+ Tasks 25, 27, 33); every moment taken for real in Task 36 |
| 4.5 globe takes: `studio-globe-flyto` (rotate, zoom, empire), `studio-globe-places` (fixed pose or sweep, the world distribution: labelled case-file places plus dots by site id, resolved by plan C, owner decision 15, filmed from a camera latitude at which one turn shows every place, a set no latitude shows refused before the take), `studio-mapbox-flyin`, `studio-mapbox-orbit` in landscape, places projected per frame; exact top-down frames with projected pins | Tasks 31, 35, 28, 26, 14 (GlobeShot tracks) |
| 4.5 source pages: scroll to the quote, DOM Range highlight, banners hidden, paywall = QuoteCard; our paper page at `#ev-NN` (a second id of a paragraph outlines the paragraph; `EVIDENCE_ID_RE` and `check_slug` imported from plans A and C) | Task 29 |
| 4.5 projection math (512-px Web Mercator with bearing, the site's perspective globe camera; the spec's word "orthographic" is to be read as that camera) | Task 26 |
| 4.6 `?video=1`: hidden panels and hover tooltips (the selected site's label stays), `--hud-scale` from `?hud=`, `window.__VIDEO`, no browser storage | Task 33 |
| 4.8 Remotion 4.0.529, every `@remotion/*` pinned | Task 1 |
| 4.8 Root with Episode + Thumbnail, calculateMetadata from timeline.json | Task 18 |
| 4.8 Episode: Sequence per scene, narration Audio per beat, music with duck callback | Tasks 10, 18 |
| 4.8 theme (colors mirror of the tokens and `src/constants/colors`, checked by a test; fonts via @remotion/fonts from local woff2, latin and latin-ext) | Task 2 (headings fall back to JetBrains Mono's latin-ext face), 17 (glyph rule on drawn strings only, owner decision 32) |
| 4.8 motion: crtOpen, bootIn, borderTrace, typeOn, digitRoll, stampSlam, ringPulse, sweep; no flicker | Task 2 |
| 4.8 blocks: PhotoPlate, ScaleDrawing, UnitGrid, EvidenceCard, SourceViewer, Meter, ClaimBoard, PlatformClip, GlobeShot, ShareCard, LowerThird, HookCaptions, Ticker, Stamp, QuoteCard, Timeline, Diagram, registry.json | Tasks 7, 12-17 (plus MapboxTopdown, MapboxFlyover, BarChart, ListCard, ScaleZoom); `registry.json` carries each block's `drawn` prop paths (owner decision 32) |
| 4.8 layout: zones, LayoutBox registration, pure overlap checker, LayoutGuard console.error JSON | Tasks 4, 11 (measured only in the brand fonts; `npm run test:gpu` proves in a real browser that the gate fires, re-run in Task 22) |
| 4.8 render.ts (bundle, selectComposition, renderMedia, chunked by frameRange, concat), lint.ts (every 6th frame at 0.5, onBrowserLog, exit != 0; plus each thumbnail teaser), still.ts per thumbnail candidate `--candidate K [--frame N]` (3840x2160 + 1280x720 < 2 MB) | Tasks 19, 20 |
| 4.8 per-render public dir, no absolute paths in props; in-frame map credits | Tasks 8 (asset paths), 12 (CreditLine), 18 (the thumbnail's credit line), 20 (asset check) |
| 4.8 vitest: overlap geometry, marker transform, timeline helpers; smoke render of a 10-s fixture, local | Tasks 4, 5, 8, 21, 22 (the smoke fixture and the graphics-only demo timeline, every block drawn by a real Chrome on the NVIDIA); Task 37 reads plan C's golden timeline |
| 4.9 thumbnails (owner decisions 24-25): three candidates for YouTube's A/B test, `thumbnails: [{frame, text}]` in timeline.json, a 2-4 word teaser in the NERV heading type clear of the duration badge, the scene's in-frame credit line, `--frame N` for a re-render | Tasks 8 (parse), 18 (Thumbnail by candidate, teaser zone, the scene's credit line in `THUMBNAIL_CREDIT_ZONE`), 20 (`still.ts --candidate K [--frame N]`, lint of the teasers), 22 |
| 4.10 topic types A-D through the block library (type B world distribution: the globe `distribution` take or PlatformClip with filters and layers; type C orders of magnitude: UnitGrid up to 1:400, ScaleZoom beyond, linear only, owner decision 31) | Tasks 13-16 (table D1), 30, 31 |
| 4.11 every Chromium on the NVIDIA with proof (captures, recorder, Remotion); NVENC `-gpu 0`, no `'if-possible'`; renderer recorded | Tasks 11 (the real-browser lint check requires the NVIDIA renderer string), 19, 20, 24, 25, 29-31, 35; doctor (with `gpu.chrome_renderer()`), `--fix-gpu`, whisper on CUDA and the ledger's renderer: plan C (see "Where this plan and plan C meet") |
| Owner picture rules: captions only in the hook; markers in their image's layer (globe: projected per frame); crop-checked markers only (the case file); no measuring lines on photos; comparisons state their basis (tested through `basisLine`); full-bleed, nothing in the YouTube control zone (text and markers); fast cursor (tested against a deadline); no agents, no title card (`chapterTagIndex` tested); platform moments via PlatformClip only; no satellite toggle in globe sections (owner correction 2026-09-26, refused by `validate_actions`, tested); the link only on the end card (a ShareCard only as the last scene, refused by `checkBlocks`, tested); a hook caption line fits one row (`HOOK_LINE_MAX_CHARS`, tested); drawn text in the brand fonts, upper case included (tested) | Tasks 10, 12, 5/13/14/35, 13, 7/16, 4, 30, 7/12, 30, 17, 10, 2/17 |

## Cross-stream requests (changes outside this stream's files)

Every request below is an item of the orchestrator's integration list, whose files no plan's tasks touch; this plan cites the items by name. Requests 1-4 are the items "CI lint-video", ".githooks/pre-push", "docs/procedures/STUDIO.md" with the Studio part of the "CLAUDE.md" item, and "docs/video-pipeline.md". The same list carries the ".gitignore" item (after merging origin/main into `feat/studio`, the line `.claude/` becomes `.claude/*` with `!.claude/skills/`, `!.claude/skills/**`, `!.claude/workflows/`, `!.claude/workflows/**` below it: git never re-includes a file under an excluded directory, so negations after `.claude/` would track nothing; `git check-ignore .claude/skills/theo-write/SKILL.md` must print nothing and exit 1, while `git check-ignore -v .claude/settings.local.json` must print the pattern `.claude/*`; with `-v` the skills file prints the negated pattern `!.claude/skills/**`, which also means "not ignored", measured 2026-09-26 in a scratch repository), the "skills and workflows" item of plan C's C2/C11, the rest of the "CLAUDE.md" item, the "docs/TRAINING_DATA_POLICY.md" item, the "commits" item (the spec, the four plans and `2026-09-26-owner-questions.md` committed with an explicit pathspec before any implementer task, this plan included, and every later plan fix the same way), the "merges" item and the "final acceptance" item.

1. **CI lint-video (`.github/workflows/ci.yml`, spec 7):** the `changes` job gains the output `video: ${{ steps.filter.outputs.video }}` and the filter `video` with `video/**`, `tests/pipeline/studio/golden_timeline.json` (Task 37's contract test reads it, so a plan-C compiler change that regenerates it must run the renderer's suite), `ancient-nerds-map/src/styles/tokens.css` and `ancient-nerds-map/src/constants/colors.ts` (`test/colors.test.ts` reads them, so a palette change on the site must run the mirror test), and `ancient-nerds-map/public/fonts/**` (`test/glyphs.test.ts` recomputes `DRAWABLE` from the woff2 files, so a font change on the site must run it). The existing `backend` filter gains `video/src/blocks/registry.json` and `video/src/theme/glyphs.ts`: plan C's Python tests and `blocks.py` read both files, so a renderer-only commit that changes a block schema, a `drawn` list or the glyph set `DRAWABLE` must run plan C's contract tests too. A job `lint-video` with `needs: [changes]`, `if: needs.changes.outputs.video == 'true'`, Node 22 and `working-directory: video` runs `npm ci`, `npx tsc --noEmit` and `npx vitest run`; no `npx remotion browser ensure`. `deploy.needs` gains `lint-video` and deploy's `if` gains `contains(fromJSON('["success", "skipped"]'), needs.lint-video.result) &&`, like the other path-filtered jobs: a push without video changes skips the job and still deploys, a red `lint-video` blocks the deploy. CLAUDE.md's "All six gates" becomes seven. The job runs on Linux: nothing `npx vitest run` collects (`test/**/*.test.ts`) needs a GPU or a browser; the real-browser checks under `video/test/gpu/` (`*.gpu.ts`, `npm run test:gpu`, Task 11) are workstation only, and CI only type-checks them through `tsc` (`test/scripts.test.ts` spawns `node --import tsx` only; `test/colors.test.ts` reads `ancient-nerds-map/src` and `test/contract.test.ts` reads `tests/pipeline/studio/`, both in the checkout).
2. **.githooks/pre-push:** for a `main` push whose diff touches a path of the `video` filter above, block with "run npm ci in video/" unless `video/node_modules/.bin/tsc` exists (the hook is fail-closed), then `run_gate` `npx tsc --noEmit` and `npx vitest run` in `video/`. Stage the hook with `git add --chmod=+x .githooks/pre-push` (`core.filemode` is false on this checkout).
3. **docs/procedures/STUDIO.md (and the Studio section of CLAUDE.md):** the renderer (`cd video && npm ci && npx remotion browser ensure`; `npm run studio` previews the demo timeline with `--public-dir ../ancient-nerds-map/public`); the scripts run as `node --import tsx scripts/<name>.ts` in `video/` and bundle into the transient `render/bundle/`; the GPU rule's proofs (`gpu:` lines, the manifest's `gpu` event); captures need an awake display (headed Chrome), which the captures hold awake but cannot wake, and Playwright in the venv (`pip install playwright`, then `playwright install chrome`); a Mapbox fly-in takes up to 20 minutes; captures are HEVC because `h264_nvenc` clips stall Remotion's decoder (Task 25); text the video draws must stay within the code points the brand font files map (`DRAWABLE` of `video/src/theme/glyphs.ts`: latin and most of latin-ext, but no `Ḫ Ḥ Ṣ Ṭ Ṛ Ṇ Ḍ ʾ ʿ`, no U+2010-2012 hyphens, no `‰`; owner question Q14): only drawn strings are checked (owner decision 32: the block props listed in `registry.json`'s `drawn`, the credits and `place`/`pin` labels of captures, captions, chapter titles, thumbnail teasers), so an original quote shown inside a captured source page, the page's own non-latin title (recorded, never drawn: SourceViewer and the credit show only the ASCII hostname) and a non-latin URL path are fine; `episode check` refuses any other drawn character; a QuoteCard's quote is drawn and must be latin; a drawn character is checked in upper case too (`ƒ` draws as `Ƒ` and is refused; `µ` is refused as written: write `micrometre`); a hook word may have at most 24 characters (`HOOK_LINE_MAX_CHARS`, one caption row); a ShareCard, the only place the link appears in the picture, may only be the last beat; platform takes never toggle the `Satellite` base map (owner correction 2026-09-26; satellite shows in the details page or a Mapbox take); a Mapbox take's `country` must be the site export's country of its place and a name the site knows; the real-browser layout-lint check (`npm run test:gpu` in `video/`, Task 11), the smoke render (Task 22) and real captures (Task 36) as the local checks.
4. **docs/video-pipeline.md:** it still describes the weekly Remotion composition this plan deletes (`WeeklyVideo`); replace that section with a pointer to the studio renderer in `video/` (`pipeline/video/timeline_builder.py` stays, described as having no renderer).

The final-acceptance item runs after the push and covers spec 8.4(c) for this plan: the Baalbek claim-5 slice rendered end to end through the `studio-video` skill (plan C's `episode init` ... `package` with this plan's captures and renderer; no upload). This plan's Tasks 22, 36 and 37 are its local preconditions, not the acceptance.

Former requests 5-8 are closed: the GPU items (doctor probes and `--fix-gpu`, faster-whisper on CUDA, the ledger's renderer string) are plan C's own tasks now, and the cue-target request is superseded by the single cue table (see "Where this plan and plan C meet").

---

## Planning verification (2026-09-26)

Every code block of this plan was applied script-driven (no hand edits) to a fresh scratch copy of this worktree's tracked files (plus plan C's Task 1 files, which the capture tasks need), task by task in plan order: for each of Tasks 1-35 the Step 1 blocks were written, the Step 2 command was run and failed as stated, the Step 3 blocks and edits were applied (every "replace" matched exactly once), the Step 4 command passed with exactly the stated count, and after every Python task the lint gate (ruff check, ruff format --check, vulture at 80) was clean. Task 1's `npm install` and Task 7's `npm run registry` were replayed with the same lockfile. Then, on the finished scratch:

- **Renderer:** `npx tsc --noEmit` clean; vitest `Test Files 22 passed (22)`, `Tests 156 passed (156)`.
- **Captures:** `106 passed, 1 skipped` (the non-Windows refusal test) on the workstation; `ruff check api/ pipeline/`, `ruff format --check`, `vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80` clean; `lint-imports`: `Contracts: 2 kept, 0 broken.`; mypy over `pipeline/studio/capture` clean (not a CI gate).
- **Backend suite** (with the CI dummy keys `LYRA_ANTHROPIC_API_KEY=ci-dummy ANTHROPIC_API_KEY=ci-dummy`): `7100 passed, 119 skipped, 57 deselected` against `6994 passed, 118 skipped` on the same scratch before Task 1 (+106 capture tests, +1 skip; the other skips are the remediation caches a worktree lacks).
- **Frontend:** `npm run type-check` clean, the recorder's `tsc -p video/tsconfig.json` clean, vitest `Test Files 111 passed (111)`, `Tests 1060 passed (1060)` (25 new), knip clean.
- **Task 22, run verbatim:** `lint clean: 100 frames checked`; `smoke.mp4` `h264`, 1920x1080, `has_b_frames=0`, `bt709`/`tv`, `60/1`, `nb_frames=600`, AAC 48 kHz; thumbnails 3840x2160 (1.9 MB PNG) and 1280x720 (88 KB JPEG); every browser printed `gpu: ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)`. A two-part render (`--chunk-frames 300`, 75 s) and a one-part render (70 s) of the same timeline matched frame by frame (PSNR at least 48.2 dB on every frame, 51.6-53.2 dB across the part boundary) and their audio was bit-identical after the AAC encode: the joins are frame- and sample-exact.
- **Task 36, real captures on the workstation** (the plan's capture code, the frontend with Tasks 33-35): top-down 3 s, source page 9 s, platform take 28 s (`2880x1620`, 60 fps, 9.48 s, search, result click and fly-to on the real site with the panels hidden and the NERV cursor), globe fly-to 428 s, places 385 s, Mapbox fly-in 1138 s, orbit 456 s (the Windows display was throttled during the globe takes); every clip HEVC `hvc1` 60 fps BT.709, every browser capture's `gpu` event names the NVIDIA. A 1800-frame timeline over these real clips (PlatformClip with `follow`, both GlobeShots, both MapboxFlyovers, MapboxTopdown with a distance line, SourceViewer) linted clean (300 frames checked) and rendered on NVENC in 4 min 34 s: `h264`, 1800 frames, BT.709, AAC 48 kHz; the platform clip's virtual camera zooms sharply onto the search box and the clicked result.
- **Tasks 33-35 again after the last edit** (`--strictPort` in `record.ts`), on a fresh copy of the frontend: all 26 replacements matched exactly once, `npm run type-check` and the recorder's `tsc` clean, the 37 tests of the touched files green, and one `studio-globe-flyto` take through that copy on port 5199: 180 frames, `renderer.json` naming the NVIDIA. (The globe and Mapbox takes above had been served by a dev server that an interrupted take of the earlier prototype had orphaned on port 5199, while each new recorder's Vite silently moved to the next port; the prototype's frontend changes are the same as this plan's, and `--strictPort` now makes such a start fail.)

Measurements behind the design decisions (all 2026-09-26, this workstation):

- **GPU.** Remotion's headless shell: `gl: 'angle'` → the NVIDIA; the default (`null`) → SwiftShader; `angle-egl` → the Basic Render Driver. Puppeteer (headed) and Playwright (headed and headless) without flags → `ANGLE (AMD, AMD Radeon(TM) Graphics ...)`, with `CHROMIUM_GPU_ARGS` → the NVIDIA. Remotion 4.0.529 maps `hardwareAcceleration: 'required'` on Windows to `h264_nvenc` (its bundled ffmpeg has it) and throws when the encoder is missing; `h264-ts` chunks have no hardware path, hence render.ts joins MP4 parts itself.
- **Clip codec.** `renderMedia` over `h264_nvenc` clips (1080p and 2880x1620, with and without B-frames, any preset or tune) timed out in Mediabunny (`Timeout while extracting frame at time 0.1sec`), stills of the same clips rendered; `libx264` and `hevc_nvenc` clips rendered. Root cause: no VUI `bitstream_restriction` in `h264_nvenc` streams (`trace_headers`), so Mediabunny infers up to 16 reorder frames. Captures are therefore `hevc_nvenc`; JPEG frames are converted to BT.709 limited range and their ICC profile dropped (colours within 4 levels after a round trip).
- **Recorder.** The first studio capture's `EBML header parsing failed`: the MediaRecorder stream had delivered 0 of 300 frames (22 and 66 in other takes), so the studio scenes grab every frame. The first Mapbox fly-in's 15-minute hang: the display slept; a re-run on a woken display completed.
- **Layout lint on real footage.** It refused the first real top-down frame (pins at 94 % and 5 % of the height put their labels under the player controls and above the safe area) and the first real places take (the Giza label at y 946): the capture now refuses such framings up front (Tasks 26, 28, 31), and both re-captures linted clean.
- **Audio.** A first design rendered the episode's audio in one audio-only pass after the video parts; on the real timeline it was still at 25 % after 3 minutes, because Remotion renders every frame for it, clips included. Per-part PCM (`separateAudioTo`) costs nothing extra and joins sample-exactly (48 kHz / 60 fps = 800 samples per frame).
- **Source pages.** A full-page screenshot of the 35,000 px Wikipedia article took 37 s on the GPU (Playwright's timeout is 30 s); the viewport shot of the same window 0.8 s.

Not verified here: the CI `lint-video` job (it does not exist yet; cross-stream request 1) and `npm ci` from a lockfile on Linux. Scratch copies were deleted afterwards (junctions removed first).

### Reconcile fix pass (2026-09-26, after the cross-plan review)

The review of plans A-D changed this plan: the BarChart range and log10 axis, per-frame globe tracks (`track` on `place` events, sweeps, the `distribution` take), the three platform actions `zoom`/`proximity`/`filter` with the measure guard, deadline-paced cursor moves, the Search-tab return of `open_details`, typed spec values and `CaptureError` for every tool, HTTP and Playwright failure, the analytics block, the paper-page anchor rule, the PNG-measured source size, the latin-ext fonts and the glyph rule, the palette mirror test, markers out of the YouTube controls, the platform-zoom sharpness limit, `chapterTagIndex`/`basisLine`, `bundle/` next to the public dir, `node --import tsx`, the AAC wording and the selected-site label in video mode. Every changed code block was re-applied script-driven to a minimal scratch copy (the capture package and its tests with the worktree's `pipeline/`, the renderer's files over junctions to the installed React/Remotion 4.0.424 and vitest, with `@remotion/fonts` 4.0.529 and a stub of `@remotion/media`, and the frontend files over its `node_modules`); the counts in the tasks are from these runs:

- **Captures, on the workstation:** `133 passed, 1 skipped` (NVENC and Playwright present); with the NVIDIA driver and Playwright hidden, as in CI: `121 passed, 13 skipped`, each with its reason; ruff check and ruff format --check clean, vulture at 80 clean, mypy clean. The cursor-pacing test's worst last move over 30 runs was 0.256 s against its 0.267 s limit (the old per-step sleep: 0.450 s); Playwright aborted `/pulse.js` through `context.route(ANALYTICS_URL_RE, ...)` against a local page.
- **Renderer:** vitest `Test Files 24`, `Tests 183`: all passed except `project.test.ts`'s lockfile test, which needs the `package-lock.json` Task 1's `npm install` writes (no install was run for this pass); `tsc --noEmit` showed only the two errors the stubs cause (`@remotion/cli/config` absent, the stubbed `<Audio>` volume callback untyped). `registry.json` regenerates to 2067 lines. `withBundle` was run with the installed `@remotion/bundler`: the bundle landed in `render/bundle` with the public dir inside it and was gone after a successful and after a failing `work`.
- **Frontend:** the `videoMode`, `screenPoint` and `studio-scenes` suites `Tests 28 passed (28)` (3 new), the app's `tsc --noEmit` and the recorder's `tsc -p video/tsconfig.json` clean.
- **Not re-run in this pass:** Task 22 (the smoke render on NVENC with Remotion 4.0.529) and Task 36 (the real captures, including the new `platform-02`, `g1e`, `g3` and `g4` takes); the real-site parts of `zoom`, `proximity`, `filter`, the Search-tab return and the recorder's per-frame tracking, which only those takes exercise; the whole-frontend vitest, knip and the backend suite. Run Tasks 22, 36 and 37 as written.

### Second fix pass (2026-09-26, after the second cross-plan review)

Changed: `HEADING` names JetBrains Mono after Orbitron (Orbitron ships no latin-ext file, so a latin-ext heading character now draws in a brand face); BarChart prints every value with its own decimals (`decimalsOf`), so a bar bound to a case-file quantity shows exactly that quantity, and "Where this plan and plan C meet" states the one quantity rule; `record_platform` and `capture_source` raise a `CaptureError` for a venv without Playwright, and `record_platform` one for a screencast without frames; Task 37 adds `video/test/contract.test.ts` over plan C's committed golden timeline (check C21); the statements about what `episode check` covers now name exactly what plans C and D implement (cue table, props schemas, references, the brand-font rule, clip length, map credits, marker boxes, meter start; the other block checks first run in `loadTimeline`); the cross-stream requests cite the orchestrator's integration list by item name and spell out how `lint-video` joins the deploy gating and the pre-push hook. Not taken: a shared block-check fixture for a Python port of the block checks (plan C narrows its claim instead of porting them) and a glyph check of its own in `capture_source` (plan C's capture step refuses any manifest string outside the brand fonts with its `glyphs.py`; a second parser of the same ranges would duplicate it).

Every changed code block was re-applied script-driven to a minimal scratch (the renderer's and the capture package's complete-file blocks, the worktree's `pipeline/`, plan C Task 1's `errors.py`; the renderer's dependencies over junctions to the installed React 18.3.1, Remotion 4.0.424, vitest 4.0.18, TypeScript 5.9.3 and tsx, with stubs of `@remotion/fonts` and `@remotion/media`; junctions removed first, then the scratch deleted):

- **Captures:** `136 passed, 1 skipped`; with Playwright hidden from the interpreter, as in CI: `test_capture_manifest.py` `16 passed`, `test_capture_sources.py` `10 passed, 5 skipped`, `test_capture_platform.py` `26 passed, 3 skipped`; ruff check, ruff format --check, vulture at 80 and mypy clean.
- **Renderer:** `registry.json` regenerated to 2067 lines; vitest `Test Files 25`, `Tests 184`, all passed except `project.test.ts`'s lockfile test (no `npm install` in the scratch), with `contract.test.ts` reading a stand-in golden file (a copy of the smoke timeline: plan C's real file does not exist before its Task 21 runs); the contract test failed as intended on a lower-case caption and on an arrow in a chapter title; the two new assertions (`valueText(1.75, 'm')`, the `HEADING` fallback) failed against the previous code and pass now; `tsc --noEmit` showed only the two known stub errors.
- **Not run in this pass:** the contract test against plan C's real golden file, Task 22 and Task 36.

### Owner-decision pass I0 (2026-09-26, owner decisions #13-#32 of the build index, section 3)

Changed, each with its tests:

- **#31, linear only.** BarChart lost `scale` (and `BarScale`, the decade ticks, the log basis line and the log check): its axis is `{lo: 0, hi}`, and a script's `scale` is refused by the schema (`props.scale: not allowed`). New scene block `ScaleZoom` (`title`, `unit`, `basis`, `small` and `large` `{id, label, value}`, 0 < small < large, at least 240 frames; cue `show <small id>` / `show <large id>`): the two quantities are bars on one linear scale, the camera pulls back linearly from the small one to the large one. `registry.json` has 18 blocks (2236 lines); `registry.test.ts` proves that no block has a `scale` prop or a log axis.
- **#32, glyph check on drawn strings only.** Every registry entry carries `drawn` (exactly `{map, platform, drawn, props}`); `checkBlocks` walks the `drawn` paths (`drawnStrings`), the drawn strings of every capture prop (`captureStrings`: credits, `place`/`pin` labels, the `page` title) and the captions, credits, chapter titles and thumbnail teasers. Tested: a SourceViewer with a Greek original quote and a Greek URL path passes; a Greek claim label and a Greek page title are refused; `registry.test.ts` proves every `drawn` pattern points at a string prop and never into a capture. The lists are those of the build index's resolution; each was checked against its component (the enum and id values a card also draws are ASCII by schema or by plan C's id rule and are not listed).
- **#24/#25, thumbnails.** `timeline.json` carries `thumbnails: [{frame, text}]`, exactly 3 (`parseTimeline`: frame inside the episode, a 2-4 word teaser); `thumbnailFrame()` (60 % into the first scene) is gone. The Thumbnail composition draws candidate K's teaser (NERV heading type, `TEASER_ZONE` inside the title-safe area and clear of YouTube's duration badge; `rules.test.ts` pins both); `still.ts --candidate K [--frame N]` writes `thumbnail_<K>_3840.png` and `thumbnail_<K>_1280.jpg`; `lint.ts` also lints each teaser (an overflowing teaser is an `overflow` violation at the candidate's frame).
- **#15, distribution dots by site id.** No code change in `globe.py` (plan C resolves `site_ids`); a new globe test pins a dot whose id is a site id: an unlabelled `place` event with that target. D2, the g4 example and the docstrings say where the dots come from.
- **D Task 29 utility duplication (build index; evidence-6).** `sources.py` imports `EVIDENCE_ID_RE` (plan A Task 2) and `config.check_slug` (plan C Task 1) and keeps neither pattern; the Dependencies table gains check A2.
- **Texts:** capture-4 (labels are the case-file place names, plan C checks), capture-5 (measure and proximity points are case-file coordinates, plan C checks), ownership-9 (cross-stream request 1: the `backend` filter gains `video/src/blocks/registry.json` and `video/src/theme/glyphs.ts`), cross-stream request 3 and D1/D2/D3/Task 29 reworded to the drawn-strings definition, the demo timeline now carries every graphics block (a ScaleZoom scene and a BarChart range bar) and Task 22 lints and renders it.

Verified on a minimal scratch (the plan's complete-file blocks written by script; for the captures the worktree's `pipeline/` plus plan C Task 1's `__init__.py`, `errors.py` and `config.py` and plan A Task 2's `theo_publishing.py`, each taken from its plan's current code block; no stand-ins for them):

- **Renderer, with a real `npm install` of Task 1's `package.json`** (the pinned Remotion 4.0.529 set, 294 packages, a fresh `package-lock.json`; no stubs, not the main checkout's 4.0.424). Before the changes: `tsc --noEmit` clean, vitest `Test Files 25 passed`, `Tests 184 passed`, `project.test.ts`'s lockfile test included. After them, rebuilt from the plan text alone: `npm run registry` writes 18 blocks (2236 lines), `tsc --noEmit` clean, vitest `Test Files 25 passed (25)`, `Tests 196 passed (196)` (24 files and 195 tests without Task 37's contract test). `contract.test.ts` read a stand-in golden file (a copy of the smoke timeline): it failed with `missing thumbnails` against the old copy and passes on the new one. Plan C's real `golden_timeline.json` does not exist yet.
- **Renders on the workstation's RTX 3080** (Task 22's commands with the scratch paths; every browser printed `gpu: ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)`): smoke lint `lint clean: 103 frames checked` (92 s); a teaser of three long words failed as intended with `{"type":"layout-violation","frame":90,"a":"thumbnail1:teaser","b":null,"reason":"overflow"}`; smoke render in two parts (91 s) `h264` 1920x1080, `has_b_frames=0`, `bt709`/`tv`, `60/1`, `nb_frames=600`, AAC 48 kHz; the three candidates 3840x2160 PNG and 1280x720 JPEG (79-93 KB), each teaser upper case on its glass at the top left. Demo lint `lint clean: 373 frames checked` (37 s), demo render 2220 frames (140 s); its contact sheet shows every graphics block drawn by the real Chrome, the BarChart range bar labelled `1,000–1,650 T` and the ScaleZoom pull-back. Measured there: a linear pull on 1:6,000 turns the small bar into a dot within the first frames of the pull-back, as the arithmetic says (recorded as owner question Q6 in `2026-09-26-owner-questions.md` and the build index's section 8; the build keeps the linear pull-back as decision 31 words it).
- **Captures:** `138 passed, 1 skipped` (the non-Windows refusal test); ruff check, ruff format --check, vulture at 80 and mypy on `sources.py` clean. The new import `pipeline.studio.capture.sources -> pipeline.lyra.theo_publishing` crosses no import-linter contract (pipeline to pipeline).
- **Cross-plan, partial:** plan C's current `script_fixtures.REGISTRY` (11 blocks, as its fixer has written it so far) equals the generated `registry.json` entry for entry (compared in Python).
- **Not run in this pass:** the build index's cross-plan re-verification (after all I0 fixers: C Task 27 against this `registry.json`, the contract test against C's regenerated golden file, the republish handshake), Task 36 (real captures), the frontend suites (no frontend file changed), the backend suite and `lint-imports`. Tasks 22 and 36 run again on the finished code before I8. Scratch copies were deleted afterwards.

### Confirm-round fix pass (2026-09-26, after the I0 confirm review)

Changed, each with its tests (the ids are those of the confirm review):

- **Page titles are data, never drawn (registry-page-title, decisions-32-page-title; owner decision 32).** A source page's own `<title>` stays in the capture's `page` event as a record and is drawn nowhere, so it is not glyph-checked: SourceViewer's address bar draws only `domainOf(url)` (`pageInfo` returns `{url, box}`), `capture_source` credits `Source page: <host>` with the new `ascii_host(url)` (IDNA, without `www.`, the string `domainOf` draws; the paper page keeps no credit), and `captureStrings` walks only the credits and the `place`/`pin` labels. `blocks.test.ts` now uses the real el.wikipedia title `Κνωσός - Βικιπαίδεια` and passes it, and refuses a Greek capture credit instead (`props.page.credits[0]: "Β" (U+0392)`); `test_capture_sources.py` pins the ASCII-host credit and the Greek title kept in the event (+1 test, `ascii_host`); the smoke fixture's source credit reads `Source page: dainst.org`. D1, D2, "Where this plan and plan C meet", Tasks 17 and 29 and cross-stream request 3 no longer name page titles as drawn and drop the "show its quote in a QuoteCard" advice. Plan C's side of the same seam: `glyphs.DRAWN_EVENT_FIELDS = {"place": "label", "pin": "label"}` (plan C's fixer). Not taken from decisions-32-page-title: drawing the case file's `evidence.source.title` in the address bar. For the type-D sources decision 32 is about, that title is often in the original script too, so SourceViewer would be refused again. SourceViewer's `drawn` stays `[]`, so `registry.json` is unchanged (18 blocks, 2236 lines) and plan C's `script_fixtures.REGISTRY` entry for SourceViewer stays `[]`.
- **Demo thumbnails before the answer (demo-thumbnails-show-the-answer).** The demo timeline's candidates sit at frames 108, 200 and 300, all before its first verdict cue (`status` at 330), as plan C's `thumbnail_problem` demands (owner decision 24); `timeline.test.ts` pins them, Task 22's demo lint names them, `teaserOf(DEMO_TIMELINE, 2)` and the 373 linted demo frames are unchanged.
- **One definition of capture ids, kinds, repo root and base URL (capture-dup-1, own-4, own-8).** `manifest.py` imports `CAPTURE_ID_RE` and `CAPTURE_KINDS` from `pipeline.studio.config` (plan C Task 1, their one home) and drops `ID_RE`/`KINDS` and its `re` import; `vite.py` imports `REPO` from `pipeline.studio.config` and `BASE_URL` from `pipeline.utils.slugs`, and keeps `PRODUCTION_URL = BASE_URL` because `sources.py`, `platform.py` and `globe.py` import that name. Check C1 now prints five lines (errors.py plus `REPO`, `CAPTURE_ID_RE`, `CAPTURE_KINDS`, `check_slug`); error messages are unchanged.
- **A Mapbox take's `country` (capture-country-3).** `studio-mapbox.ts` `checkCountry` throws `unknown country <x>` before `prepareMapbox` when the site's `getCountryCode` knows no code, so the recorder exits 1 and `record_globe` raises its `CaptureError` (+1 test in `studio-scenes.test.ts`); `prepareMapbox` is unchanged for the Shorts. D2 and the globe docstring state the rule; plan C binds `country` to the site export.
- **No satellite toggle (decisions-no-satellite-toggle, owner correction 2026-09-26).** `validate_actions` refuses `toggle_layer` with the label `Satellite` in any case, before any side effect (+1 parametrized case; `test_record_platform_validates_before_starting_anything` also proves it through `record_platform`, with no `captures/` written).
- **Texts:** the Footage docstring names HEVC from `hevc_nvenc` on GPU 0 (decisions-gpu-stale-text); Task 16 and the I0 record name the 1:6,000 ScaleZoom question as owner question Q6 (registry-scalezoom-question-unrecorded).
- **Not taken here:** capture-doc-2 (it would keep the page title drawn and checked, against owner decision 32 and the two major issues above; spec 4.3 and index row #32 stay as written). The spec, index and owner-questions edits of registry-spec-block-text-stale, render-3, decisions-gpu-stale-text (spec part), registry-scalezoom-question-unrecorded (the Q6 row), own-1, own-2, own-6 and own-9 are the orchestrator's; this plan's text already matches them.

Verified on a minimal scratch built by script from the plan text (every complete-file block and all 26 frontend replacements matched once; the worktree's `pipeline/` and `ancient-nerds-map/` without `public/` and `node_modules`, the frontend's `node_modules` as a junction; plan C Task 1's `__init__.py`, `errors.py` and current `config.py` with `CAPTURE_ID_RE`/`CAPTURE_KINDS`, and plan A Task 2's `theo_publishing.py`, each from its plan's current code block):

- **Renderer, with a real `npm install` of Task 1's `package.json`** (Remotion 4.0.529, 294 packages): `npm run registry` writes 18 blocks (2236 lines), `tsc --noEmit` clean, vitest `Test Files 25 passed (25)`, `Tests 196 passed (196)` (`contract.test.ts` on a stand-in golden file, a copy of the smoke timeline). With the old `page` line put back into `captureStrings`, the Greek-title test fails as intended.
- **Captures:** `140 passed, 1 skipped` over the ten capture test files (`test_capture_sources.py` 17, `test_capture_platform.py` 30); ruff check, ruff format --check, vulture at 80 and mypy clean. `test_the_cursor_is_fast_even_when_each_move_takes_time` (unchanged by this pass) failed in 2 of 5 runs while parallel agents loaded the workstation (0.35 s against its 0.267 s limit) and passed on every quiet re-run.
- **Frontend:** `studio-scenes.test.ts` `Tests 12 passed (12)` (with `videoMode` and `screenPoint`: 29), the recorder's `tsc -p video/tsconfig.json` and the app's `tsc --noEmit` clean.
- **Not run in this pass:** Tasks 22 and 36 (NVENC renders and real captures), the backend suite, `lint-imports` (the new imports are pipeline to pipeline), the whole-frontend vitest and knip, plan C's glyph tests with the narrowed `DRAWN_EVENT_FIELDS`, and the build index's cross-plan re-verification. Scratch copies were deleted afterwards (junction removed first).

### Second confirm-round fix pass (2026-09-27, after the second confirm review)

Changed, each with its tests (the ids are those of the review):

- **Hook caption lines fit one row (timeline-hook-caption-width).** `video/src/captions.ts` exports `HOOK_LINE_MAX_CHARS = 24` on a line of its own, and `captionLines(captions, maxWords = 4, maxChars = HOOK_LINE_MAX_CHARS)` also starts a new line before a word that would make the line (its words joined by single spaces, punctuation included) longer than 24 characters; the four-word, punctuation and pause breaks stay. +1 test (`ARCHAEOLOGISTS FOUND SOMETHING IMPOSSIBLE` gives `ARCHAEOLOGISTS FOUND` / `SOMETHING IMPOSSIBLE`; the existing expectations are unchanged). Task 10's intro records the fontTools measurement and the HookCaptions docstring the limit. Plan C mirrors the constant and refuses a hook word longer than 24 characters before voice (its fixer; its Task 27 reads the line with a regex).
- **Upper case in the glyph rule (timeline-glyph-rule-ignores-css-uppercase).** `unsupportedChar` also tests every code point of `ch.toUpperCase()`, and `glyphReason` names what the character turns into (`"µ" (U+00B5) draws as "Μ" (U+039C) in upper case, which has no glyph in the brand fonts (latin and latin-ext only)`). `glyphs.test.ts` covers `µ` and `ẖ`, and a new blocks test refuses the teaser `Smaller than 1 µm?` at `thumbnails[0].text`. Within the two brand ranges exactly five characters change verdict: U+00B5 `µ`, U+01F0 `ǰ`, U+1E96 `ẖ`, U+1E98 `ẘ` and U+1E99 `ẙ`. Node 22.17 and Python 3.13.5 (Unicode 15.1) give the same list, so plan C's `str.upper()` mirror agrees.
- **ShareCard only as the last scene (decisions-sharecard-end-card).** `checkBlocks` reports `scene <id> (ShareCard): ShareCard is the end card; only the last scene may use it` for a ShareCard on any scene but the last. +1 blocks test: a ShareCard at b10 of the demo timeline is the only error, so the last scene's ShareCard passes. The D1 row, D3, the ShareCard docstring and Task 17's intro state the rule. The demo timeline keeps its ShareCard last; the smoke fixture has none.
- **The distribution camera shows every place (capture-distribution-pose).** `distribution_pose` no longer takes the places' mean latitude. It takes the latitude nearest the midpoint of their lowest and highest latitude (the midpoint itself, or a whole degree within ±45) at which every place is admissible (`_faces_camera`). A dot is admissible within the horizon less 5° (`DISTRIBUTION_DOT_REACH_DEG`, 60.8° at 2.44). A labelled place is admissible when projection.py's globe camera draws it inside `PLACES_BAND` at some camera longitude of the turn. When no latitude admits them all, `scene_input` raises before any side effect with `<id>: places [...] cannot face the camera in one turn of the globe; split the distribution`. The camera longitude is unchanged. +2 tests: the Rapa Nui case gives 10.45, a labelled place at -40° among dots at 45° gives -14.0, and 70°N with -66° is refused through `record_globe`, with no `captures/` written. The existing test keeps 10.42 and 161.82. D2, Task 31's intro and the module docstring describe the rule.
- **Task 32 after Task 29 (capture-task32-order).** Row 29 of the Dependencies table now reads "29 (source pages) and 32 (package exports, imports `sources.py`)" with check A2. The recommended order reads "do Tasks 30 and 31 first if it prints nothing; Task 32 comes after Task 29". Task 32's intro says why.
- **Counts:** renderer 24 files and 198 tests before Task 37 (+3), 25 and 199 with it; `test_capture_globe.py` 28 (CI 27 + 1 skip); the capture suite `142 passed, 1 skipped` (CI `129 passed, 14 skipped`). The Spec coverage table names the end-card, caption-row and upper-case rules and the distribution pose.
- **Not taken here (no plan-D change; the orchestrator's or another plan's):** registry-q6-still-unrecorded, own-r2-q6-unrecorded and decisions-31-q6-unrecorded, which cover the Q6 row in the owner-questions file and index section 8 plus the #22/#23 marks. Task 16 and the I0 record already point at Q6 and keep the linear pull-back. Also registry-spec-4.3-4.8-stale and render-spec-stale-nvenc-text (spec edits), and own-r2-ci-backend-filter (index I4; cross-stream request 1 already asks for the `backend` filter lines). Then own-r2-i2-i6-skill-content (index I2/I6; cross-stream request 3 already carries the D-side rules: hook word length, upper case, end card, no satellite toggle, the Mapbox `country`), own-r2-d7-heading (index row D7; this plan's heading already says 18) and own-r2-i0-gate-list (index 4.2/4.4). Plan C's halves of the caption, upper-case and end-card items belong to plan C's fixer.

Verified on a minimal scratch built by script from the plan text: every complete-file block of `video/`, `pipeline/studio/capture/` and its tests; the worktree's `pipeline/`; plan C Task 1's `__init__.py`, `errors.py` and `config.py`, and plan A Task 2's `theo_publishing.py`, each from its plan's current block; the frontend's `package.json`, `video/record.ts`, `tokens.css` and `constants/colors.ts`. The renderer ran on the Remotion 4.0.529 install of the previous pass, made from the same `package.json` and lockfile.

- **Renderer:** `npm run registry` writes 18 blocks (2236 lines, unchanged). `tsc --noEmit` is clean. vitest gives `Test Files 25 passed (25)` and `Tests 199 passed (199)`; `contract.test.ts` read a stand-in golden file (a copy of the smoke timeline), and `project.test.ts`'s lockfile test is included. Each new test failed against the code without its fix: without the character budget, `captionLines` gives one line; without the upper-case test, `µ` passes; without the end-card rule, a b10 ShareCard passes.
- **Captures:** `142 passed, 1 skipped`. With the NVIDIA driver and Playwright hidden, as in CI, `129 passed, 14 skipped`, each skip with its reason. ruff 0.15.11 check, ruff format --check, vulture at 80 and mypy over `pipeline/studio/capture` are clean. With the mean-latitude pose put back, both new globe tests fail: 41.17 instead of 10.45, and the refusal test reaches the recorder.
- **Probes:** 499 dots near 45°N plus a labelled Machu Picchu give `cam_lat` 16.42 in 5 ms. The mean-latitude pose would sit at 44.88, where Machu Picchu never enters the band. Task 36's `g4` spec gives 20.14 (its midpoint). A fontTools re-run on `orbitron-700.woff2` confirmed Task 10's numbers: an average capital of 56 px, 1126 and 2046 px, 5 of 18 four-word lines over 1440 px, a widest 24-character line of 1220 px, and 24 × `M` at 1518 px.
- **Not run in this pass:** Tasks 22 and 36 (NVENC renders and real captures; the distribution pose changes which latitude the `g4` take is filmed from), the frontend suites (no frontend file changed), the backend suite, `lint-imports` (no new import), plan C's mirrors of the three shared rules, and the build index's cross-plan re-verification. Scratch copies were deleted afterwards.

### I14 pass (2026-09-27, build index item I14, round-3 review)

Changed, each with its tests (the ids are those of the round-3 review):

- **Small values print exactly (registry-decimalsof-misprints-small-values).** BarChart's `decimalsOf` counts the exact decimals of the number's shortest form, exponent form included, with no cap: `String(x)` split at `e`, the mantissa's decimals minus the exponent, at least 0. Before, it read the decimals of `String(x)` and capped them at 6, so 1.5e-7, 6.6e-7 and 1e-10 printed `0 m` and 0.0000015 printed `0.000002 m`. No check caught it: `0 m` is short, and plan C compares values only. +1 test in `blocks-infographics.test.ts` with the three `valueText` cases (17 tests). ScaleZoom prints through the same `valueText`. A value too long for its box fails the layout lint as `overflow`. A value beyond 100 decimals (below 1e-100) makes `toLocaleString` throw a `RangeError`, so the render fails instead of printing another number. Task 16's intro states the rule. Plan C and `registry.json` are unchanged.
- **The thumbnail keeps its scene's credit (timeline-thumbnail-drops-map-and-photo-credits, render-thumbnail-drops-map-credit).**
  - `CreditLine` (Task 12) takes an optional `zone: Rect` (default `ZONES.credit`). It aligns its line to the frame edge the zone is nearer to: right in the episode, as before, and left in the thumbnail's bottom-left zone. The alignment rule is not in the index text and is recorded here.
  - `Thumbnail.tsx` exports `THUMBNAIL_CREDIT_ZONE = {x: 96, y: 984, w: 800, h: 32}` and `creditsAt(timeline, frame)`: the `timeline.credits` texts of the scene with `from <= frame < from + durationInFrames`.
  - After `EpisodeVisuals` (which keeps `credits={false}`), it draws `` <CreditLine id={`thumbnail${candidate}:credit`} text={mergeCredits(credits)} zone={THUMBNAIL_CREDIT_ZONE} /> `` inside the scenes' registry. It draws nothing for a scene without credits.
  - The line is not measured in lint mode. It is the scene's own line (same text, same box size), which the episode lint measures. In the teaser's registry, the lint's player-controls rule would refuse it: y 984 lies in the episode's control band, which a thumbnail does not have.
  - `rules.test.ts`: the teaser-zone test also asserts `contains(SAFE, THUMBNAIL_CREDIT_ZONE)`, zero overlap with `TEASER_ZONE`, `DURATION_BADGE` and `ZONES.lowerThird`, and the width and height of `ZONES.credit`. +1 test for `creditsAt` (15 tests).
  - Texts: D4, the thumbnails bullet of "Where this plan and plan C meet", the File Structure row, the intros of Tasks 12 and 18, and the Thumbnail and `still.ts` docstrings now read "without captions, ticker or chapter tag; with the scene's in-frame credit line (spec 4.8)". Task 22 Step 3 expects the photo credit on candidate 1, `© Mapbox © Maxar` on candidate 3 and no credit on candidate 2. The Spec coverage rows 4.8 and 4.9 name the thumbnail's credit line.
- **Counts:** renderer 24 files and 200 tests before Task 37, 25 files and 201 tests with it.
- **Not changed here:** plan C's C9 text and spec 4.9. These are the orchestrator's I14 text edits, as are the other spec items at the end of the index's section 3.

Verified on a minimal scratch built by script from the plan text. It held the 95 complete-file blocks of `video/`, `registry.json` from `npm run registry`, the site's `tokens.css` and `constants/colors.ts`, and a stand-in golden file (a copy of the smoke timeline). The worktree's Remotion 4.0.529 `node_modules` was mounted as a junction.

- **Before the changes:** `tsc --noEmit` clean, `Test Files 25 passed (25)`, `Tests 199 passed (199)`. The new tests fail against the old code: `valueText(1.5e-7, 'm')` returns `0 m`, and the two thumbnail tests fail on the missing `THUMBNAIL_CREDIT_ZONE` and `creditsAt`.
- **After:** `npm run registry` writes 18 blocks (2236 lines, unchanged), `tsc --noEmit` is clean, and vitest reports `Test Files 25 passed (25)`, `Tests 201 passed (201)`. Probes: 6.6e-7 prints `0.00000066 m`, 1e21 prints `1,000,000,000,000,000,000,000 m`, 12742 prints `12,742 m`, and 1e-101 throws `RangeError: maximumFractionDigits value is out of range.`
- **On the RTX 3080** (every browser printed `gpu: ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)`): the demo timeline with two credits on scene b01. For candidate 1 (frame 108, b01), `still.ts` draws `Photo: Smoke Test (CC BY-SA 4.0) · © Mapbox © Maxar` left aligned at the bottom left, clear of the teaser. For candidate 2 (frame 200, b02, no credits) it draws none. `lint.ts` prints `lint clean: 373 frames checked`.
- **Not run in this pass:** Task 22 on the smoke fixture (its HEVC clips), Task 36, and the capture and frontend suites (none of their files changed). Scratch copies were deleted afterwards (junctions removed first).

### Task 2 review fix (2026-09-27, glyph rule from the files' cmap)

An adversarial review of Task 2's commit e48172e found the glyph rule unsound: it trusted the declared `unicode-range` of fonts.css, but Google's subset files do not map their whole range. Measured with fontTools 4.65 and confirmed in Remotion's own chrome-headless-shell (CDP `CSS.getPlatformFontsForNode`, the exact faces of `fonts.ts`): `Ḫattuša`, `Kṛṣṇa`, `Ḥatḥor`, `Baʿal`, `non‑breaking` (U+2011) and `5‰` passed the old rule and drew those characters in Arial, Courier New or Times New Roman. The old plan text ("a latin-ext letter in a heading (… Ḫattuša …) is drawn … never by a system font") was wrong.

Changed (implemented in the follow-up commit to e48172e, on `feat/studio`):

- `glyphs.ts` keeps `LATIN_RANGE` and `LATIN_EXT_RANGE` for `fonts.ts` and adds `DRAWABLE` (single-quoted, one line, like the two ranges): the code points the loaded files map, each face's cmap within its unicode-range, common to the heading, body/hud and serif stacks (JetBrains Mono ∩ Cormorant Garamond, 389 code points in 43 runs), plus tab, line feed and carriage return. `unsupportedChar` and `glyphReason` keep their signatures and message text and test against `DRAWABLE`.
- New `video/scripts/fontCoverage.ts` (a WOFF2 cmap reader on Node's `zlib.brotliDecompressSync`, no new dependency; the drawable set from `FONTS`, `HEADING`, `BODY`, `SERIF`) and `video/scripts/glyphs.ts` (prints the constant). The reader matched fontTools' `getBestCmap()` exactly on all 40 woff2 files of `ancient-nerds-map/public/fonts`.
- `glyphs.test.ts`: 6 tests instead of 3; the drift test recomputes `DRAWABLE` from the site's fonts; `Ḫattuša` is now a refusal case, with `Kṛṣṇa`, `Ḥatḥor`, `Baʿal`, U+2011 and `‰`; the upper-case example is `ƒ` → `Ƒ` (`µ`, `ǰ`, `ẖ` are refused as written now: no loaded file maps them).
- Browser proof: every character `unsupportedChar` accepts drew only in Orbitron, JetBrains Mono or Cormorant Garamond in all four styles (heading, body, hud, serif), line feed and tab included (white-space normal and pre-wrap); every refusal case above drew a system font.
- Texts: Task 2's intro and blocks, Task 17's intro and its two glyph tests (`Ḫattuša` refused; `Set ƒ/8?` for the upper-case message, count unchanged), "Where this plan and plan C meet", the File Structure rows, cross-stream request 1 (the `video` filter gains `ancient-nerds-map/public/fonts/**`) and request 3 (STUDIO.md wording), the suite totals (203 before Task 37, 204 with it).
- Plan C (Task 17's `glyphs.py` mirrors `DRAWABLE` instead of the two ranges; its glyph tests; Task 27's contract regex), the build index's contract row and I4 filter, and owner question Q14 (a font for dot-below and breve-below transliterations) were revised in the same pass.

### Task 11 review fix (2026-09-27, the lint measures in the brand fonts, proved in a real browser)

An adversarial review of Task 11's commit 2d44956 found two gaps, both confirmed.

1. **Font race.** Remotion 4.0.529 mounts the composition (`remotion_setBundleMode`, `make-page.js`) without waiting for delayRender handles, and `remotion_setFrame` to the frame a tab already shows returns the same state (`TimelineContext.js`), so nothing renders again. `loadFont` adds a face to `document.fonts` only after its fetch and `load()`. The first frame of every render tab (its `initialFrame`), and so the whole one-frame Thumbnail lint, was measured in whatever fonts had arrived at mount. Measured in chrome-headless-shell with the Thumbnail's teaser box (1368x332, `heading(104)`): `WHO ENGINEERED BAALBEK MONOLITHS?` takes two lines in the fallback font and three in Orbitron. With the fonts held back 2.5 s, the old code missed that overflow on frames 0 and 1 of a two-tab lint and on the one-frame teaser.
2. **No proof that the gate fires.** The four tests covered only pure helpers, and Task 22 only ever expects `lint clean`.

Changed (commits 4bcfafd and 86e306e on `feat/studio`):

- `theme/fonts.ts`: `loadBrandFonts()` keeps its signature and stores the `Promise.all` of the `loadFont` calls. The new `brandFontsReady()` returns it and throws if `loadBrandFonts()` was never called (Task 18's `Root.tsx` calls it on import, unchanged).
- `layout/LayoutBox.tsx`: a lint-mode `LayoutProvider` holds a `delayRender` handle from mount until `brandFontsReady()` resolves. It then renders again with `fontsReady`, so every `LayoutBox` measures and `LayoutGuard` reports in that commit, and it releases the handle in its own layout effect, which runs after its children's. `useLayoutBox` measures only when `registry.enabled && fontsReady`. The context is `{registry, fontsReady}` and is read with `useLayoutState()`, which replaces `useRegistry()` (no other task used it). `Registry.set` throws `LayoutBox <id> was measured outside lint mode` on a disabled registry.
- `layout/LayoutGuard.tsx`: it reports only once `fontsReady` is set, and throws when it is rendered under a registry that does not measure.
- `test/guard.test.ts`: the tautological `measures only in lint mode` test is replaced by `refuses a box outside lint mode and keeps nothing` (still 4 tests).
- New real-browser check `video/test/gpu/` (`guard.gpu.ts`, `guardFixture.tsx`, `vitest.config.ts`), run with `npm run test:gpu` (new script in `video/package.json`). It is workstation only: `npm test` collects only `*.test.ts`, so CI's `lint-video` never sees it. It bundles the fixture with the seven font files, opens every browser with `gl: 'angle'` and requires the NVIDIA renderer string. Then it renders the way `lint.ts` does (`renderFrames`, scale 0.5, violations from `onBrowserLog`), with the font files held back 2.5 s. It requires exactly these lines, as built by `violationLine`, on all 6 frames with concurrency 2: `teaser` overflow, `edge` outside-safe and `captions`/`lt` overlap, plus `drop` in the controls from frame 3. It also requires no lines outside lint mode, and on a Thumbnail-like one-frame composition exactly the teaser's overflow. The scene there, under a disabled registry, is not reported, and a fitting two-line teaser gives nothing. Measured 2026-09-27: 3 passed in about 36 s. Against 2d44956 the same check fails, missing the two first-frame overflows and the one-frame teaser overflow.
- Texts (rewritten in place by a follow-up commit, as Task 2's review fix and the I14 pass rewrote their tasks; e32b57e had only appended this section, which left the task blocks describing the old code):
  - Task 11: its Files list, its intro (the font race and the real-browser check), its `guard.test.ts`, `LayoutBox.tsx` and `LayoutGuard.tsx` blocks (now the committed files), and a new Step 5 with the three `video/test/gpu/` files as complete-file blocks. Step 5 runs `npx tsc --noEmit && npm run test:gpu` (expected `Tests  3 passed (3)`) and records the measured failure without the font hold. The commit step became Step 6 and adds the three files.
  - Task 2: the intro says why `brandFontsReady()` exists, and the `fonts.ts` block carries `brandFonts` and `brandFontsReady()`.
  - Task 1: the `package.json` block has the `test:gpu` script, with a sentence on `test` against `test:gpu`.
  - Task 22: the intro and Step 2 run `npm run test:gpu` before the lints, and Step 2's Expected names its result.
  - The File Structure rows of `package.json`, `fonts.ts` and `LayoutBox.tsx`/`LayoutGuard.tsx`, and a new row for `video/test/gpu/`.
  - The Spec coverage rows 4.8 layout and 4.11, cross-stream request 1 (CI collects only `*.test.ts`; `test/gpu` is type-checked, never run) and request 3 (STUDIO.md names `npm run test:gpu` among the local checks).
- Checked 2026-09-27: each complete-file block of `video/package.json`, `video/src/theme/fonts.ts`, `video/src/layout/LayoutBox.tsx`, `video/src/layout/LayoutGuard.tsx`, `video/test/guard.test.ts` and the three `video/test/gpu/` files occurs once in this plan and is byte-identical to the committed file (a script extracted the blocks and compared them). `npm run test:gpu` then gave `Tests  3 passed (3)` (34.5 s). On a scratch copy with the 2d44956 `LayoutBox.tsx`, `LayoutGuard.tsx` and `fonts.ts` it gave `Tests  2 failed | 1 passed (3)`: 19 lines instead of 21, and `[]` for the one-frame teaser.
- Still open, for Task 20 or 22 and not done here: once Task 20's `lint.ts` exists, a planted timeline run through `lint.ts` should show exit code 1 with exactly its violation lines, next to the `lint clean` runs.
