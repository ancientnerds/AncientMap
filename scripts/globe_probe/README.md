# Globe load probe

`probe.py` measures how `/globe.html` loads, in Chromium driven by Python Playwright. It is
the yardstick for the acceptance criteria A1-A6 in
`docs/superpowers/specs/2026-09-23-globe-load-design.md`. The pure parts (byte ledger,
local routing, `fields=globe` projection, long-task window, image diff) are tested in
`tests/scripts/test_globe_probe.py`.

```bash
PY=C:/PythonProjects/AncientMap-globeload/.venv/Scripts/python.exe   # or any venv with playwright + Pillow
$PY -m playwright install chromium      # once per Playwright version (1.63 needs chromium-1243)

$PY scripts/globe_probe/probe.py load --target prod  --device desktop --gpu
$PY scripts/globe_probe/probe.py load --target prod  --device phone --cpu 4 --gpu
$PY scripts/globe_probe/probe.py nogl --target prod
$PY scripts/globe_probe/probe.py shot --target prod  --pose 10,51,2.44 --dpr 1 --gpu
$PY scripts/globe_probe/probe.py shot --target prod  --pose 10,51,1.31 --dpr 2 --gpu --block-mapbox
$PY scripts/globe_probe/probe.py diff A.png B.png
```

Each run writes `output/globe_probe/<yyyymmdd-hhmmss>-<command>-<target>-<device>[-label]/`
(gitignored), which holds `report.json` and the screenshots. `diff` writes `diff.png` (the
difference amplified 4x) and `diff.json`.

## What every browser run does

- It opens `https://ancientnerds.com/globe.html?demo=1`. `?demo=1` registers `window.__DEMO`.
  Outside the demo API it changes only two Mapbox settings (tile cache size and
  `preserveDrawingBuffer`).
- **Tracker.** An init script replaces `window.umami` with a recorder. `/pulse.js` and
  `/api/pulse` are aborted, so the real tracker never loads and no probe event reaches
  production Umami. Every `track()` call ends up in `report.json` → `events`, with its
  `performance.now()` time.
- **Service workers are blocked.** Every run is a first visit. The worker's precache
  (~8.8 MB with the start tiers) is not part of any number. Playwright routing also turns off Chromium's HTTP cache.
- **Mapbox.** `--block-mapbox` aborts `api.mapbox.com` and `events.mapbox.com`, because every
  Mapbox init is a billed map load. It is on by default for `load` and `nogl` and off for
  `shot`. Pass `--block-mapbox` to a `shot` at a pose close to the switch distance (1.304),
  so that the Three.js view stays on screen.
- **Browser.** `--gpu` runs headed Chromium on the real GPU, with the flags that
  `ancient-nerds-map/video/record.ts` proved on the RTX 3080. It adds
  `--disable-backgrounding-occluded-windows`, because a covered window would stall the
  frame-counted warp. A probe of hidden-tab behaviour must drop that flag. Without `--gpu` the
  run is headless. `gl_renderer` in the report names the renderer that was actually used.
- **Devices.** `desktop` is 1920×1080 at DPR 1 with a Windows Chrome UA. `phone` is a Pixel 7:
  412×915 at DPR 2.625, touch, and an Android Mobile UA. The phone gate shows, the probe
  screenshots it (`gate.png`, after `document.fonts.ready`) and then clicks
  `.mobile-action-globe`.
- **Extra query.** `--query basemap=med` appends to the page URL (e.g. to pin a basemap tier).
  `--label x` names the run directory.

### `load`

| field | how it is measured |
|---|---|
| `globe_ready_ms` | `t` of the `globe_ready` track call (page `performance.now()`, navigation = 0) |
| `ready_after_gate_ms` | phone only: `globe_ready` minus the capture-phase click on `.mobile-action-globe` |
| `network.bytes_before_ready` | CDP `Network.loadingFinished.encodedDataLength` of every request that finished before `globe_ready`. CDP's monotonic clock is mapped to page time through `requestWillBeSent.wallTime` and `performance.timeOrigin`. `in_flight_at_ready` lists what was still loading. |
| `warp_end_ms` | the first 50 ms poll at which `__DEMO.isReady()` returns true (warp done and dots faded in) |
| `long_tasks_before_ready`, `long_tasks_after_warp_30s` | `PerformanceObserver({type: 'longtask', buffered: true})`: count, max, total and every task > 200 ms (A2 uses the second one) |
| `network.http_errors`, `failed`, `blocked` | status ≥ 400, network failures, and requests the probe aborted |
| `console_errors`, `page_errors` | console `error` messages and uncaught exceptions (Mapbox tokens redacted) |

`--cpu N` sets CDP `Emulation.setCPUThrottlingRate`. `--net fast4g` sets DevTools'
"Fast 4G" preset (9 Mbit/s × 0.9 down, 1.5 Mbit/s × 0.9 up, 165 ms latency); the default
is no emulation. Screenshots: `ready.png` at `globe_ready` and `end.png` 30 s after the
warp. The exit code is 1 when `globe_ready` or the warp end does not arrive within
`--timeout` (240 s); the report is written in that case too.

### `nogl`

An init script makes `getContext('webgl2')` return `null` on every canvas, including
`OffscreenCanvas`. This is how a browser without WebGL 2 behaves. After `--wait` seconds
(default 3) the probe writes a screenshot (`nogl.png`) and a report. The report says
whether the unsupported screen is present (`unsupported_screen`: text "…show the 3D globe…")
and when it appeared (`unsupported_seen_ms`, 50 ms polling; A4 requires ≤ 2 s). It also
records the body text, the events and the page errors.

### `shot`

The probe waits for `__DEMO.isReady()`. With `--after-bg` it also waits for a `globe_bg`
event of each task in `--bg-tasks` (default `layers,basemap`). A device whose maximum
basemap tier equals its start tier never sends `basemap`, so pass `--bg-tasks layers`
there. Then the probe calls `__DEMO.hideAllUI()` (the `demo-mode` class hides the panels),
`setAutoRotate(false)`, with `--labels` `setGeoLabels(true)` (the geo labels are off at start),
and `setCameraPose(lng, lat, distance)`. It waits `--settle`
seconds (1.5) and screenshots `.globe-container > canvas`. The screenshot covers the
canvas area, so the footer links (IMPRINT PRIVACY TERMS) are in the image, the same in
every shot. The report records `__DEMO.getCameraState()`.

### `diff`

Pillow computes the mean absolute difference over RGB (0-255) and the share of pixels whose
largest channel difference exceeds `--threshold` (24/255). Images of different sizes are
refused.

## `--target local`

Run `npm run build` first. Leave `VITE_UMAMI_WEBSITE_ID` unset: `grep -c pulse.js
dist/globe.html` must print 0. Set `VITE_MAPBOX_ACCESS_TOKEN` only in the process
environment, and only if Mapbox has to start.

The page still loads under `https://ancientnerds.com`. `context.route` answers from
local files:

- **From `ancient-nerds-map/dist/`:** html, `/assets/**`, `/sw.js`, fonts and every other
  built file.
- **From the worktree's `public/data/layers/globe/`:** `/data/layers/globe/*`.
- **From production:** everything else, i.e. `/api/`, `/goto/`, every other `/data/` file
  (including the `dist/data/snapshots` copy) and third parties.

Bytes of locally answered files are counted the way production nginx would send them
(`ancientnerds-nginx-config`): gzip level 6 for its `gzip_types` from 1024 bytes on, raw
for images and woff2. The report marks those requests with `local: true`. Check: the same
bundle measured 88.73 MB locally and 88.74 MB on production.

**Simulated `fields=globe`.** Before the run, the probe asks production for
`/api/sites/all?limit=2&fields=globe`.

- If the sites still carry detail keys (U2 not deployed), every
  `/api/sites/all?…fields=globe…` request is answered by fetching the full production
  payload and projecting it to `id,n,la,lo,s,t,p,pn,c`. The probe prints
  `[probe] SIMULATED fields=globe …` and lists the request under `simulated` in the report.
- Once production honours `fields`, the request goes to production unchanged.

Measured 2026-09-23: 5,004 sites, 1,013,199 B raw, 331,385 B gzip-6. The full payload is
3.14 MB on the wire.

Caveats:
- Local responses bypass network emulation.
- Local timing is not production timing: files come from disk, and production uses HTTP/2.
- Only the page target's network is seen. Requests a web worker makes itself would be
  missing from the byte count.

## Baseline: production before any globe-load change (2026-09-23)

Production served commit `8a957b45` (`main-BQbULAlk.js`). Machine: RTX 3080 Laptop GPU,
`ANGLE … Direct3D11`, `MAX_TEXTURE_SIZE` 16384, Chromium 153 (Playwright 1.63). All runs
blocked Mapbox except the two start-pose shots.

| probe | globe_ready | bytes before ready | long tasks before ready | after the warp (30 s) |
|---|---|---|---|---|
| `load --device desktop --gpu` | 15.18 s (warp end 17.49 s) | 88.74 MB, 78 requests | max 5,837 ms, total 12.7 s, 7 over 200 ms | 0 long tasks |
| `load --device phone --cpu 4 --gpu`, run 1 | 61.90 s (60.25 s after the gate) | 71.58 MB, 79 requests | max 36,698 ms, total 58.0 s, 14 over 200 ms | max 145 ms, 37 tasks |
| `load --device phone --cpu 4 --gpu`, run 2 | 66.07 s (64.17 s after the gate) | 71.58 MB, 79 requests | max 8,059 ms, total 24.2 s, 14 over 200 ms | max 96 ms, 3 tasks |
| `load --target local --device desktop --gpu` (same code, local build) | 15.12 s | 88.73 MB | max 6,303 ms | 0 long tasks |

Where the desktop's 88.74 MB go:

| MB | what |
|---|---|
| 2 × 25.06 | `coast_hires.geojson`, fetched once by the front loader and once by the back loader |
| 17.02 | `satellite_high.webp` |
| 7.32 | `ne_10m_rivers.geojson` (preload, layer off) |
| 5.05 | `ne_10m_lakes.geojson` (preload, layer off) |
| 3.31 | `gray_dark_high.webp` |
| 3.14 | `/api/sites/all` |
| 2 × 0.68 | the GitHub border file |
| 0.46 | the Mapbox chunk |

The phone gets `satellite_med` and `gray_dark_med` and otherwise the same files. Both
devices request `/data/basemaps/gray_dark_low.png` (the `globe.html` preload) and get a 404.

`nogl --target prod`:
- No unsupported screen. The body text is only `IMPRINT PRIVACY TERMS`: a black screen.
- One page error, `Error creating WebGL context.`, and a `js_error` event.

Screenshots (`shot --target prod --gpu`):
- `--pose 10,51,2.44 --dpr 1` → 1920×1080
- `--pose 10,51,2.44 --dpr 2` → 3840×2160
- `--pose 10,51,1.31 --dpr 2 --block-mapbox` → 3840×2160

The images are not committed; run the same commands against production to recreate them.

Noise floor: the same shot taken twice on production, then `diff`.

| pose | mean abs diff | share > 24/255 |
|---|---|---|
| 2.44, DPR 1 | 0.054 | 0.060 % |
| 2.44, DPR 2 | 0.016 | 0.017 % |
| 1.31, DPR 2 | 0.0002 | 0 % |

A comparison above these values is a real difference.

## `strip_upload_check.py` — the basemap upload in a real WebGL2 context

Bundles `ancient-nerds-map/src/services/basemapUpgrade.ts` with the project's esbuild, runs it
against three's real `WebGLRenderer` and reads the texels back through a framebuffer: the strip
upload and the whole upload must match the old `<img>` upload (rows mirrored, because the
ImageBitmap textures pair with the `(u, v)` UVs in `sceneInit.ts`) at level 0 and mip level 1,
with no GL error and the strip source never registered in the renderer. It also times every
strip copy, the allocation and the out-of-memory check.

```bash
$PY scripts/globe_probe/strip_upload_check.py                                  # pattern 1024x512, headless
$PY scripts/globe_probe/strip_upload_check.py --gpu --rows 256 --image public/data/basemaps/gray_dark_high.webp
$PY scripts/globe_probe/strip_upload_check.py --browser webkit --tolerance 1   # needs `playwright install webkit`
```

Measured 2026-09-24: all six basemap files byte-identical in Chromium (SwiftShader and a D3D11
GPU) and WebKit 26.6; the synthetic pattern differs by 1 in ~0.1 % of the channels in WebKit
only (WebKit colour-tags the PNG `canvas.toBlob` writes).
