# Globe load: visible first, everything else in the background

Status: approved by Martin on 2026-09-23 ("Empfehlungen umsetzen", including removing the 3 s splash
minimum; the phone gate stays). Branch `globe-load`, worktree `C:/PythonProjects/AncientMap-globeload`.

## 1. Why

Measured on production between 2026-09-17 and 2026-09-23 (Umami, Playwright probes with the tracker
stubbed out):

| | desktop | phone / tablet |
|---|---|---|
| loads of `/globe.html` | 66 | 55 |
| reached `globe_ready` | 38 (58 %) | 9 (16 %), iPhone 0 of 10 sessions |
| time to `globe_ready` p25 / p50 / p75 | 12 / 29 / 42 s | 28 / 44 / 68 s |

Root causes, each reproduced:

1. **89 MB before `globe_ready`** on desktop, 72 MB on a phone (after the gate). `coast_hires.geojson`
   (25 MB, 543 k points, 15 decimals) is fetched and parsed twice, once by `loadFrontLayer` and once by
   `loadBackLayer`; `.geojson` is served as `application/octet-stream` without gzip; the border file
   comes twice from `raw.githubusercontent.com`; `satellite_high.webp` (17 MB, 16383×8192) blocks
   `texturesReady` although satellite mode is off at start; the rivers/lakes "preload" (12 MB) starts
   2 s after mount, during the loading screen, for two layers that are off.
2. **8.2 s main-thread block** from decoding and uploading the two 16k textures through
   `HTMLImageElement` (`?basemap=low` → longest task 0.5 s). With `createImageBitmap` the decode moves
   off the main thread; the upload of one 16k texture then costs ~0.56 s, one 8k texture ~0.14 s
   (RTX 3080; weaker GPUs several times more).
3. **No WebGL → black screen.** `new THREE.WebGLRenderer()` throws `Error creating WebGL context`
   inside a React effect, the whole tree unmounts, only the footer remains. One Edge visitor reloaded
   seven times on 2026-09-22.
4. **Serial third-party geolocation before anything else.** `loadData` awaits `ipwho.is`, then
   `geojs.io`, without a timeout, and `<Globe>` mounts only after `locationReady`. Costs ~1.5 s per
   visit; a hanging provider hangs the globe.
5. **Sites payload 3.1 MB gzip, 10 MB raw, TTFB 1.0–1.2 s** (`/api/sites/all`, serialised and
   gzipped on every request although the dict is cached). The dots need ~9 % of it.
6. **Mapbox GL (463 kB gzip JS, second WebGL context, style, fonts, tiles, a billed map session)
   initialises during the loading screen**, although it is only shown from 66 % zoom on.
7. **A 3 s minimum splash** (`MIN_SPLASH_DURATION`) on top of all of it.
8. The service-worker rule for basemaps matches `\.(jpg|png)$`; the files are `.webp`, so repeat
   visits re-download them.

## 2. Goal and acceptance criteria

Everyone either gets the globe fast and stable, or a clear message why their device cannot show it.
The first frame after the loading screen looks exactly like today. Nothing appears that the visitor
did not switch on; what is missing loads in the background after the globe is shown, and only
refines things that are already visible, below the point where the difference is visible.

Acceptance (measured with the same probes as the baseline, see §9):

- A1. Bytes transferred before `globe_ready`: ≤ 3.5 MB on desktop and on the emulated phone
  (baseline 89 / 72 MB).
- A2. No main-thread task > 200 ms between the end of the warp intro and 30 s later on the desktop
  probe (baseline: 8.2 s tasks during loading; the background upgrade must not reintroduce them).
- A3. `globe_ready` on the desktop probe ≤ 4 s (baseline 16–18 s); on the emulated phone (CPU ×4,
  after the gate) ≤ 10 s (baseline 86 s).
- A4. A browser without WebGL 2 shows the unsupported screen within 2 s, with the reason and links;
  never a black screen.
- A5. A screenshot of the first frame after the warp (fixed camera) is visually identical to today's
  (same basemap mip level, coastline and borders within half a device pixel).
- A6. At the closest Three.js zoom before the Mapbox switch, coastlines/borders/basemap are visually
  identical to today's once the background tier has arrived.
- A7. All existing gates green: pytest gate suite, ruff, ruff format, lint-imports, vulture, mypy (if
  touched), type-check, vitest (under Node 20), knip, `npm run build`, `npm run build:ssr`,
  size-limit, generate_shared_data --verify.

## 3. Constraints

- The phone gate in `App.tsx` stays, text and layout unchanged. A phone layout for the globe is a
  separate project.
- No design changes beyond removing the 3 s splash minimum; the fade-out stays.
- CLAUDE.md: no fallback code, no silent catch-and-continue. Timeouts on third-party calls and an
  explicit capability check are not fallbacks; returning empty data on error is.
- `*.geojson` is Git LFS and the LFS budget is exhausted: new data files use `.json`.
- No nginx change: `.json` is already `application/json` and in `gzip_types`.
- `pipeline/` ships in two images; anything the Lyra image imports must import without `markdown`
  and `nh3`.
- Work only in the worktree. The main working tree belongs to a running DB-audit session.

## 4. What is visible at the first frame (the critical set)

At start the camera sits at `CAMERA.MAX_DISTANCE` = 2.44 and Mapbox takes over at 66 % zoom
(distance ≈ 1.50). The Three.js globe is therefore never shown closer than ~0.5 R altitude
(≈ 1.7 km per device pixel on a DPR-2 1080p screen, ≈ 3.4 km at DPR 1).

Critical set, loaded before the overlay fades:

| item | today | new |
|---|---|---|
| JS | incl. mapbox-gl 463 kB | without mapbox-gl |
| sites | full, 3.1 MB gzip | `fields=globe`, ≈ 0.25 MB gzip |
| sources, labels.json, fonts | unchanged | unchanged (label fonts preloaded) |
| gray basemap | 16k (desktop) / 8k (touch) | **start tier**: 8k desktop, 4k touch/phone |
| satellite basemap | blocks start | not in the critical set |
| coastlines | 25 MB × 2 | **start tier** ≈ 0.5 MB gzip, fetched once |
| borders | 2 × GitHub 10m | self-hosted, simplified, fetched once |
| rivers/lakes preload | during loading | background |

At the start distance the GPU samples the same mip level from an 8k texture as from a 16k one (a
hemisphere of ≥ 4096 texels onto ≤ 1000 CSS px), so the start tier renders identically (A5).

## 5. Components

### 5.1 Globe layer build (`scripts/build_globe_layers.py`, outputs under `public/data/layers/globe/`)

Offline, reproducible build from `public/data/layers/coast_hires.geojson` (read from a checkout that
has the LFS content) and Natural Earth `ne_10m_admin_0_boundary_lines_land` (downloaded once by the
script from the pinned upstream URL, never at runtime):

- `coast_start.json`: Douglas-Peucker at the tolerance where the start view deviates < 0.5 device px
  (≈ 0.02°), coordinates rounded to 3 decimals.
- `coast_detail.json`: tolerance chosen so the closest Three.js view deviates < 0.5 device px
  (≈ 0.005–0.01°; the final value is picked by the A6 screenshot comparison and recorded in the
  script).
- `borders.json`: the 10 m border lines at the detail tolerance.

Format: GeoJSON `FeatureCollection` so the existing feature walker in `vectorRenderer.ts` keeps
working; compact separators. The script prints point counts and gzip sizes and is idempotent. A test
checks the committed files parse, carry the expected geometry types and stay under their size budgets.

### 5.2 Vector layers (`config/vectorLayers.ts`, `Globe/rendering/vectorRenderer.ts`, `Globe.tsx`)

- `getLayerUrl` maps coastlines and borders to the new files: start tier for the initial load,
  detail tier from the background queue. `coast_hires.geojson` is used only when Mapbox is
  unavailable (init failed, or offline without cached tiles) and the camera goes closer than the
  Mapbox switch distance — the view that exists today in exactly that case.
- One fetch and one `JSON.parse` per layer file. Front and back layers are built from the same parsed
  data (today each loader fetches and parses on its own).
- Swapping start → detail replaces the line geometry in place with the same material and opacity, so
  there is no fade or flash.
- The rivers/lakes preload moves into the background queue.
- `services/VectorLayerCache.ts` (offline downloads) lists the new files so offline mode keeps
  working.

### 5.3 Basemap textures (`utils/deviceTier.ts`, `hooks/globe/useTextureLoading.ts`, new `services/basemapUpgrade.ts`)

- `deviceTier` gains `getStartTier()` (touch/phone or small screen → `low`, otherwise `med`, never above
  the GPU limit) next to the existing maximum tier.
- Only the gray basemap of the start tier is in the critical set; `texturesReady` depends on it alone.
- Decode through `createImageBitmap` (off the main thread). Orientation must stay exactly as today
  (A5 screenshot); if the ImageBitmap path needs different UVs or `flipY` handling, that is solved
  and tested once, for every basemap texture.
- Background: satellite at the start tier (so the satellite button responds at once); on desktops
  whose maximum tier is `high`, the 16k gray upgrade; the 16k satellite only while satellite mode is
  on. 16k uploads go in horizontal strips via `renderer.copyTextureToTexture` into a pre-allocated
  texture, at most one strip per frame, mipmaps generated once after the last strip, then swapped
  into the uniform (A2). The old texture is disposed after the swap.
- If the satellite toggle is used before its texture is there, the toggle waits for it and shows its
  pending state; the view does not switch to an empty texture.

### 5.4 Sites: globe fields first, details in the background

- API (`api/routes/sites.py::get_all_sites`): new query parameter `fields` with values `all`
  (default, today's payload) and `globe` (`id, n, la, lo, s, t, p, pn, c` — exactly what dots,
  filters, tooltips and the list need at start; verified against the consumers). Clients that do
  not send `fields` get today's payload; an old API ignores the unknown parameter and returns the full payload, which the new
  client reads correctly (rolling deploy safe).
- The response body is serialised and gzip-compressed once per cache entry and served as bytes with
  `Content-Encoding: gzip` when the client accepts it (TTFB target < 100 ms on a warm cache). Cache
  key includes `fields`. Invalidation paths that clear the `sites:all:*` keys keep working.
- Frontend (`data/DataStore.ts`, `data/sites.ts`): initial load with `fields=globe`; the background
  queue's first item fetches the full payload and merges the detail fields into the existing site
  objects (same ids, no new dots, no re-render storm).
- Consumers that need detail fields wait for them instead of showing half data: the search (matches
  descriptions) and the site popup (description, image, citations). Waiting shows the existing
  loading state; nothing renders empty and then fills in.
- `SourceLoader` (non-default sources on demand) and offline storage keep the full payload.

### 5.5 Startup sequencing (`App.tsx`, `sceneInit.ts`)

- The geolocation lookup starts at once and runs in parallel; `<Globe>` mounts without waiting for it.
  Each provider request gets an `AbortController` deadline; the result, when it arrives before the
  warp starts, sets the warp target (camera start/target recomputed from the same formula
  `initializeScene` uses today). If there is none by then, the existing default target is used — the
  same behaviour as a failed lookup today.
- Focus links (`?site=` / focus mode) keep their exact start position.
- `MIN_SPLASH_DURATION` goes; the overlay fades as soon as sites and the critical layers are ready.
  `updateLoadingStatus`' 3 s minimum per message stays (display only, never delays loading).

### 5.6 Mapbox lazily (`Globe/rendering/mapboxEffects.ts`, `services/MapboxGlobeService.ts` importers, `hooks/globe/useMapboxSync.ts`)

- `mapbox-gl` is loaded with a dynamic `import()` from the background queue and initialised there.
  The service exposes a state: `idle | loading | ready | failed`.
- Until the state is `ready`, the orbit controls do not zoom closer than the Mapbox switch distance,
  so nobody sees the Three.js globe at a zoom it never showed before. When the state becomes `ready`
  while the zoom is already at the threshold, the auto-switch runs (today it only re-evaluates on
  zoom changes).
- `failed` keeps today's behaviour without Mapbox (the Three.js globe zooms on; the high-resolution
  coastline loads on demand, §5.2). The failure is logged and tracked (§5.9), never swallowed.

### 5.7 Background queue (new `services/globeBackgroundQueue.ts`)

A small sequential scheduler: starts when the warp intro has completed (`warpProgressRef >= 1`),
runs one task at a time, yields to `requestIdleCallback` (with a timeout) between tasks, pauses while
the tab is hidden. Order:

1. full site details (search and popup wait on this)
2. Mapbox import + init
3. coastline + border detail tier
4. satellite at start tier
5. 16k gray upgrade (desktops with maximum tier `high`)
6. rivers + lakes preload

Each task reports start/end; failures are logged with the task name and tracked, the queue moves on.
The queue is unit-tested for order, idle gating, pause/resume and failure isolation.

### 5.8 Reliability (`App.tsx`, new `components/GlobeUnsupported.tsx`, new `components/GlobeErrorBoundary.tsx`)

- Capability check before `<Globe>` mounts: a throw-away canvas must yield a `webgl2` context (three
  r182 needs WebGL 2) and `MAX_TEXTURE_SIZE ≥ 4096`. Otherwise the unsupported screen: what is
  missing, how to enable hardware acceleration, links to the pages that work without the globe
  (Stories, Radar, Journal, Database), in the visual language of the existing phone gate.
- An error boundary around the globe: any error while the globe starts (renderer creation, shader
  compile, a failed critical fetch) shows an error screen with the phase, the message and "Reload the
  globe", instead of unmounting the page.
- Loading watchdog: if no critical item progressed for 20 s, the overlay hint changes to "This is
  taking unusually long" with the reload button. Loading itself continues.
- Background tabs: loading progress must not depend on `requestAnimationFrame` (a load in a hidden
  tab completes its fetches and uploads when shown).

### 5.9 Measurement (`analytics/index.ts`, `pipeline/umami_db.py`, `pipeline/stats_analysis.py`, dashboard `GlobeReach`)

New events (extend `EventName` first):

- `globe_gate` `{choice: globe|stories|radar|journal|lyra|db}` — the phone gate's buttons.
- `globe_unsupported` `{reason}` — the capability check failed.
- `globe_error` `{phase, message}` — the error boundary or a failed critical load.
- `globe_abandon` `{ms, phase}` — `pagehide`/`visibilitychange→hidden` before `globe_ready`, sent
  once per load with `navigator.sendBeacon` semantics of the tracker.
- `globe_bg` `{task, ms}` — background task finished (one event per task per load, small).

The GlobeReach panel keeps its current numbers and adds the split of the loads that did not reach the
globe: stopped at the phone gate, unsupported, error, left while loading (with the median wait), no
signal (the crash signature). Tests for the SQL shape and the pure functions, like the existing ones.

### 5.10 Caching (`ancient-nerds-map/vite.config.ts`)

- Basemap runtime rule matches `.webp`; `/data/layers/globe/*.json` gets a `CacheFirst` rule. URLs of
  critical assets carry the build hash (`CACHE_BUSTER`) so a deploy never serves stale data.
- No change to navigation handling (`navigateFallbackDenylist` untouched).

## 6. Error handling

Every new async path either completes or surfaces: critical failures go to the error boundary (§5.8),
background failures are logged with the task name and tracked as `globe_error{phase:"bg:<task>"}` and
leave the already-visible globe untouched. No `catch {}` that returns empty data.

## 7. Out of scope

Phone layout for the globe UI; GPU-compressed textures (KTX2/Basis) — revisit if the new events
still show crashes or stalls on iOS after this ships; Mapbox billing changes.

## 8. Risks

- `createImageBitmap` orientation/colour handling differs between engines → one tested code path,
  WebKit checked with Playwright's WebKit engine.
- `copyTextureToTexture` strip uploads must respect three's texture state → spike first, unit test
  plus probe (A2).
- Mapbox state transitions (zoom clamp, auto-switch on ready) → tests on the effect functions plus a
  probe that zooms in right after the reveal.
- The sites field split touches search and popup → tests for the waiting behaviour.

## 9. Verification

- Unit tests (vitest, pytest) per component, written first.
- Probes (`scripts/globe_probe/` — Playwright, tracker stubbed so no test event reaches Umami):
  bytes and time to `globe_ready` (desktop, emulated phone with CPU ×4), long tasks after the warp,
  no-WebGL screen, first-frame screenshot vs production, closest-zoom screenshot vs production. Run
  against a local production build with `/api` routed to production.
- All gates of A7 locally, then CI.
- After deploy: `commit` of `http://localhost:8000/` equals HEAD, probes against production, and the
  new events arriving in Umami.
