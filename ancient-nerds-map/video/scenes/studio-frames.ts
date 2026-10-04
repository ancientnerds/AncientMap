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
 * A page that stops drawing (a take on a sleeping display waited 15 minutes for its
 * first frame, 2026-09-26, in the headed Chrome of that time) must fail fast: every
 * wait for an animation frame is bounded by NO_FRAME_MS. The recorder's Chrome is
 * headless now, so no display has to be awake for a take.
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
/** Longest wait for an animation frame before the take fails (the page is not drawing). */
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
    reject(new Error('no animation frame for ${NO_FRAME_MS / 1000} s: the page is not drawing'));
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
