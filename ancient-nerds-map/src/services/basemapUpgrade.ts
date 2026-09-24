/**
 * Basemap textures: decode off the main thread, upload whole (start tier) or
 * in horizontal strips (everything from 8k up), swap into the basemap
 * materials, and load again after a WebGL context restore.
 *
 * Every bitmap is closed once it is on the GPU. Keeping the start tier's open
 * so three could re-upload it after a context restore held 32 MiB (low),
 * 128 MiB (med: phones, Retina laptops) or 512 MiB (high: tall DPR-2 windows)
 * of memory for the page's whole life, for a context loss most sessions never
 * have. A restore decodes the start tier again instead (restoreGray): the file
 * is in the HTTP cache and the service worker's 'basemaps' cache.
 *
 * The call sequences follow three r182 (node_modules/three/src, checked
 * 2026-09-23):
 * - `copyTextureToTexture(src, dst, box, at, 0, 0)` takes the texSubImage2D
 *   path only while `src` is unknown to the renderer (`properties.has(src)`
 *   false; WebGLRenderer.js copyTextureToTexture), so the strip source is never
 *   uploaded, rendered or passed to `initTexture`. Subrects of an ImageBitmap
 *   through UNPACK_SKIP_ROWS are specified in WebGL 2.0 §5.35.
 * - After every level-0 copy three calls `generateMipmap` when
 *   `dst.generateMipmaps` is true. `getMipLevels` sizes the immutable storage
 *   from `texture.mipmaps.length` when the flag is off (WebGLTextures.js), so
 *   the destination is allocated from a list of level sizes (full chain, no
 *   data, no mip pass over empty storage), strips run with the flag off, and
 *   one final one-row copy with it on builds the mips once.
 * - The texture cache key contains `generateMipmaps`, `flipY`, filters and
 *   colour space and is only re-read on a version bump: the destination is
 *   never `needsUpdate`d again after the allocation and ends with the
 *   allocation-time flag values, otherwise three would silently reallocate.
 * - Orientation (texture brief §3.1, option B): WebGL ignores UNPACK_FLIP_Y
 *   for ImageBitmap sources, so texture row r holds image row r (north at
 *   t = 0), and the basemap UVs in sceneInit are `(u, v)` with v = 0 at the
 *   north pole. Every basemap texture comes from `decodeBasemap`; an <img>
 *   upload would now render upside down. Proven against a real WebGL2 context
 *   (byte-identical to the old <img> path, rows mirrored) by
 *   scripts/globe_probe/strip_upload_check.py.
 * - Option A (`imageOrientation: 'flipY'`) was dropped: Chrome applies every
 *   createImageBitmap option on the main thread. Measured 2026-09-24 on
 *   gray_dark_high/satellite_high (16383x8192): flipY 660-760 ms,
 *   colorSpaceConversion 'none' 360-420 ms, premultiplyAlpha 'none'
 *   135-190 ms of long task; default options none. The files are opaque,
 *   untagged VP8, so premultiplication and colour conversion leave the bytes
 *   as they are.
 * - Synchronous GL queries wait for the GPU process: a `getError` right after
 *   the 16k allocation measured 458-499 ms. The one out-of-memory check runs a
 *   frame after the mip copy. `isContextLost` reads a flag, it is no query.
 * - GL error flags cannot be attributed to a call, and a strip upload leaves
 *   its allocation's flag unread for 30+ frames. The gray upgrade (queue task)
 *   and the satellite (the toggle, its max-tier effect) run independently, so
 *   one basemap upload runs at a time per context (UploadLock, from allocation
 *   to check): a check reads the flags of its own upload, and a failed
 *   allocation is never committed by a load that did not check it.
 *
 * Plain `fetch`, not offlineFetch: the service worker's basemap rule
 * (src/pwa/runtimeCaching) serves these URLs from the 'basemaps' cache, which
 * every offline download fills with the gray tiers (services/GlobeStartCache)
 * and the 'Satellite' download with the satellite tiers.
 */

import * as THREE from 'three'
import { getBasemapAssets, tierRank, type BasemapTier } from '../utils/deviceTier'

export type Uploader = Pick<THREE.WebGLRenderer, 'initTexture' | 'copyTextureToTexture' | 'getContext'>
export type BasemapKind = 'gray' | 'satellite'
export type BasemapUniform = 'uGrayBasemap' | 'uSatellite'

/** Rows per strip: 16 MiB of RGBA for a 16383-wide file, 8 MiB for 8192. */
export const STRIP_ROWS = 256

const UNIFORM: Record<BasemapKind, BasemapUniform> = { gray: 'uGrayBasemap', satellite: 'uSatellite' }

// ---------------------------------------------------------------------------
// Decode and upload
// ---------------------------------------------------------------------------

/** Fetches and decodes a basemap file off the main thread. The bitmap is closed if the load was aborted meanwhile. */
export async function decodeBasemap(url: string, signal: AbortSignal): Promise<ImageBitmap> {
  const res = await fetch(url, { signal })
  if (!res.ok) throw new Error(`basemap ${url}: HTTP ${res.status}`)
  // Default options: any option runs on the main thread in Chrome (see the header).
  // Bitmap row 0 is the image top (north); sceneInit's UVs sample it at v = 0.
  const bitmap = await createImageBitmap(await res.blob())
  if (signal.aborted) {
    bitmap.close()
    throw signal.reason
  }
  return bitmap
}

/** The sampling settings of every basemap texture (those of the old TextureLoader path). */
function configureBasemapTexture(texture: THREE.Texture): void {
  texture.colorSpace = THREE.SRGBColorSpace // the shader writes raw output; NoColorSpace would brighten the map
  texture.flipY = false // ignored for ImageBitmap by the spec; false keeps a non-conforming engine harmless
  texture.premultiplyAlpha = false
  texture.generateMipmaps = true
  texture.minFilter = THREE.LinearMipmapLinearFilter
  texture.magFilter = THREE.LinearFilter
  texture.anisotropy = 16
}

/**
 * three's texStorage2D only logs; a GPU that cannot hold the texture leaves a
 * silent GL error. One check per upload turns it into a failure (flags stay
 * set until read, so a later check still sees it). WebGL may hold several
 * flags and getError returns them in no fixed order, so all are drained: only
 * the first call waits for the GPU process. Flags cannot be attributed to a
 * call, so anything but OUT_OF_MEMORY is logged with its code rather than
 * failing a load it may not belong to; CONTEXT_LOST_WEBGL belongs to the
 * context-loss path (releaseOnContextLost / reloadAfterContextRestored).
 */
function assertNoOutOfMemory(renderer: Uploader, what: string): void {
  const gl = renderer.getContext()
  const flags: number[] = []
  for (let e = gl.getError(); e !== gl.NO_ERROR; e = gl.getError()) {
    if (e !== gl.CONTEXT_LOST_WEBGL) flags.push(e)
  }
  if (flags.includes(gl.OUT_OF_MEMORY)) throw new Error(`${what}: GPU out of memory`)
  if (flags.length > 0) console.error(`[basemap] ${what}: GL error flags`, flags.map(f => `0x${f.toString(16)}`).join(', '))
}

/** Uploads a bitmap in one go (texStorage2D + texSubImage2D + mips) now, not inside the next render. */
export function uploadWhole(renderer: Uploader, bitmap: ImageBitmap): THREE.Texture<ImageBitmap> {
  const texture = new THREE.Texture(bitmap)
  configureBasemapTexture(texture)
  texture.needsUpdate = true
  renderer.initTexture(texture)
  try {
    assertNoOutOfMemory(renderer, `basemap upload ${bitmap.width}x${bitmap.height}`)
  } catch (err) {
    texture.dispose() // the storage is allocated already
    throw err
  }
  return texture
}

export interface Strip { y: number; h: number; last: boolean }

/** Horizontal strips of `rows` rows covering `height`; bitmap rows [y, y+h) go to texture rows [y, y+h). */
export function stripPlan(_width: number, height: number, rows: number): Strip[] {
  const strips: Strip[] = []
  for (let y = 0; y < height; y += rows) {
    const h = Math.min(rows, height - y)
    strips.push({ y, h, last: y + h >= height })
  }
  return strips
}

/** One animation frame, or the abort reason. Frames stop in hidden tabs, so an unmount there must not leave it pending. */
export function nextAnimationFrame(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason)
      return
    }
    const onAbort = () => {
      cancelAnimationFrame(id)
      reject(signal.reason)
    }
    const id = requestAnimationFrame(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    })
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

export interface StripOptions {
  rows: number
  nextFrame: (signal: AbortSignal) => Promise<void>
  signal: AbortSignal
}

/**
 * Uploads a bitmap one strip per frame into a pre-allocated texture, then
 * builds the mipmaps in a frame of their own. Closes the bitmap either way; on
 * failure or abort the destination is disposed. Allocation uses the bitmap's
 * own size (16383 for the high files: a 16384 allocation would leave a zero
 * column at the antimeridian that bleeds into every mip).
 */
export async function uploadInStrips(renderer: Uploader, bitmap: ImageBitmap, opts: StripOptions): Promise<THREE.Texture> {
  const { width, height } = bitmap
  const dst = new THREE.Texture<{ width: number; height: number }>()
  dst.image = { width, height }
  configureBasemapTexture(dst)
  // Full chain from a size list: texStorage2D(levels) without the mip pass three
  // would run over the empty storage when generateMipmaps is on. three reads only
  // width/height of the entries while source.dataReady is false (never `data`).
  const levels = Math.floor(Math.log2(Math.max(width, height))) + 1
  const empty = new Uint8Array(0)
  dst.mipmaps = Array.from({ length: levels }, (_, i) => ({ data: empty, width: Math.max(1, width >> i), height: Math.max(1, height >> i) }))
  dst.generateMipmaps = false // also: no generateMipmap after each strip
  dst.source.dataReady = false // allocate only
  dst.needsUpdate = true // version 0 -> 1, or setTexture2D skips it
  const src = new THREE.Texture(bitmap)
  const box = new THREE.Box2(new THREE.Vector2(), new THREE.Vector2())
  const at = new THREE.Vector2()
  try {
    if (opts.signal.aborted) throw opts.signal.reason
    renderer.initTexture(dst) // texStorage2D(levels, SRGB8_ALPHA8, width, height)
    for (const strip of stripPlan(width, height, opts.rows)) {
      box.min.set(0, strip.y)
      box.max.set(width, strip.y + strip.h)
      at.set(0, strip.y)
      renderer.copyTextureToTexture(src, dst, box, at, 0, 0)
      await opts.nextFrame(opts.signal)
      if (opts.signal.aborted) throw opts.signal.reason
    }
    // Mips once: re-copy the last row with the flag on, then back to its allocation value.
    dst.generateMipmaps = true
    box.min.set(0, height - 1)
    box.max.set(width, height)
    at.set(0, height - 1)
    renderer.copyTextureToTexture(src, dst, box, at, 0, 0)
    dst.generateMipmaps = false
    await opts.nextFrame(opts.signal)
    if (opts.signal.aborted) throw opts.signal.reason
    assertNoOutOfMemory(renderer, `basemap ${width}x${height}`)
    return dst
  } catch (err) {
    dst.dispose()
    throw err
  } finally {
    bitmap.close()
  }
}

/**
 * Points `uniform` of every material at `texture`, then disposes what it
 * replaced. In that order: a disposed texture still referenced by a uniform
 * would be re-uploaded from its (possibly closed) image at the next render.
 */
export function swapUniform(materials: THREE.ShaderMaterial[], uniform: BasemapUniform, texture: THREE.Texture | null): void {
  const previous = new Set<THREE.Texture>()
  for (const material of materials) {
    const old = material.uniforms[uniform].value as THREE.Texture | null
    if (old && old !== texture) previous.add(old)
    material.uniforms[uniform].value = texture
  }
  previous.forEach(old => old.dispose())
}

/**
 * One basemap upload at a time (see the header). `acquire` resolves with the
 * release once every earlier holder has released; an abort while waiting
 * rejects at once with the abort reason and does not hold up later callers.
 */
export class UploadLock {
  private tail: Promise<void> = Promise.resolve()

  acquire(signal: AbortSignal): Promise<() => void> {
    const previous = this.tail
    let release!: () => void
    const released = new Promise<void>(resolve => { release = resolve })
    this.tail = previous.then(() => released)
    return new Promise((resolve, reject) => {
      const onAbort = () => {
        release()
        reject(signal.reason)
      }
      if (signal.aborted) {
        onAbort()
        return
      }
      signal.addEventListener('abort', onAbort, { once: true })
      void previous.then(() => {
        if (signal.aborted) return // rejected and released by onAbort
        signal.removeEventListener('abort', onAbort)
        resolve(release)
      })
    })
  }
}

// ---------------------------------------------------------------------------
// Per-kind state and the loaders
// ---------------------------------------------------------------------------

/** What one basemap kind holds on the GPU, what is loading, and what was asked for. */
export class BasemapState {
  /** Tier of `texture`; null while none is committed. */
  tier: BasemapTier | null = null
  /** The texture the materials sample. */
  texture: THREE.Texture | null = null
  /** Highest tier ever asked for; a context restore asks for it again. */
  wanted: BasemapTier | null = null
  private flights = new Map<BasemapTier, { ctrl: AbortController; handedOver: boolean; done: Promise<void> }>()

  /** A texture of `tier` would raise what is held (never replace a higher tier with a lower one). */
  accepts(tier: BasemapTier): boolean {
    return this.tier === null || tierRank(tier) > tierRank(this.tier)
  }

  /**
   * Runs `load` for `tier` unless that tier or a higher one is held; a caller
   * asking for a tier that is already loading joins that load, unless that load
   * was aborted: joining it would reject with the old reason. Its decode still
   * runs (createImageBitmap cannot be aborted), so the new load starts once the
   * aborted one has settled - one full-size bitmap per tier at a time, however
   * often the satellite is switched off and on during a decode - and does not
   * start at all if it was aborted while it waited. The load's signal aborts
   * with the caller's signal (the promise rejects with its reason) or with
   * `abortAll` (the promise resolves: the context restore or the unmount that
   * cut it short owns what happens next, it is not a failure of the load).
   */
  run(tier: BasemapTier, signal: AbortSignal, load: (signal: AbortSignal) => Promise<void>): Promise<void> {
    if (this.wanted === null || tierRank(tier) > tierRank(this.wanted)) this.wanted = tier
    if (!this.accepts(tier)) return Promise.resolve()
    const running = this.flights.get(tier)
    if (running && !running.ctrl.signal.aborted) return running.done
    if (signal.aborted) return Promise.reject(signal.reason)
    const ctrl = new AbortController()
    const onAbort = () => ctrl.abort(signal.reason)
    signal.addEventListener('abort', onAbort, { once: true })
    const flight = { ctrl, handedOver: false, done: Promise.resolve() }
    // The aborted load's own caller receives its outcome; this one only waits for it to end
    const started = running
      ? Promise.allSettled([running.done]).then(() => {
        if (ctrl.signal.aborted) throw ctrl.signal.reason
        return load(ctrl.signal)
      })
      : load(ctrl.signal)
    flight.done = started
      .catch((err: unknown) => {
        if (flight.handedOver) return
        throw err
      })
      .finally(() => {
        signal.removeEventListener('abort', onAbort)
        if (this.flights.get(tier) === flight) this.flights.delete(tier)
      })
    this.flights.set(tier, flight)
    return flight.done
  }

  /**
   * Aborts every running load of this kind; their callers' promises resolve
   * (handed over). The flights stay listed until they settle (run's `finally`
   * drops them): their decodes still run, and the restore's request for the
   * same tier waits for them like for any aborted flight.
   */
  abortAll(reason: unknown): void {
    this.flights.forEach(flight => {
      flight.handedOver = true
      flight.ctrl.abort(reason)
    })
  }
}

export interface BasemapContext {
  renderer: Uploader
  /** Every material with the basemap samplers: main, the four sections, back. */
  materials: THREE.ShaderMaterial[]
  tiers: { start: BasemapTier; max: BasemapTier }
  gray: BasemapState
  satellite: BasemapState
  /** Shared by both kinds: one upload at a time, so each out-of-memory check reads its own upload's flags. */
  uploads: UploadLock
  nextFrame: (signal: AbortSignal) => Promise<void>
  /** A satellite texture was committed to the materials (true), or the context loss dropped it (false). */
  onSatelliteTexture: (onGpu: boolean) => void
}

/**
 * Loads `tier` of `kind`, strips from med up unless `whole` (the start gray: on
 * the GPU before the render that needs it), and commits it unless a higher tier
 * landed meanwhile. While the context is lost nothing is decoded: the upload
 * would go nowhere, and the restore asks for `wanted` (run recorded it) again.
 */
async function loadTier(ctx: BasemapContext, kind: BasemapKind, tier: BasemapTier, signal: AbortSignal, whole = false): Promise<void> {
  if (ctx.renderer.getContext().isContextLost()) return
  const bitmap = await decodeBasemap(getBasemapAssets(tier)[kind], signal)
  let release: () => void
  try {
    release = await ctx.uploads.acquire(signal)
  } catch (err) {
    bitmap.close() // aborted while another upload ran: never uploaded
    throw err
  }
  let texture: THREE.Texture
  try {
    if (!whole && tierRank(tier) >= tierRank('med')) {
      texture = await uploadInStrips(ctx.renderer, bitmap, { rows: STRIP_ROWS, nextFrame: ctx.nextFrame, signal })
    } else {
      try {
        texture = uploadWhole(ctx.renderer, bitmap)
      } finally {
        bitmap.close() // on the GPU now; a context restore drops this texture instead of re-uploading it
      }
    }
  } finally {
    release()
  }
  const state = ctx[kind]
  // Uploaded into a lost context: the storage is gone, and releaseOnContextLost
  // has run or is about to. The restore asks for `wanted` again.
  if (!state.accepts(tier) || ctx.renderer.getContext().isContextLost()) {
    texture.dispose()
    return
  }
  swapUniform(ctx.materials, UNIFORM[kind], texture)
  state.tier = tier
  state.texture = texture
  if (kind === 'satellite') ctx.onSatelliteTexture(true)
}

/**
 * The critical-path gray: the start tier, uploaded whole before the first
 * render needs it, assigned only once it is on the GPU. Uploaded into a lost
 * context it is not committed and the load resolves: the restore loads it
 * again (restoreGray), like a load the loss cut short (handed over).
 */
export function loadStartGray(ctx: BasemapContext, signal: AbortSignal): Promise<void> {
  const tier = ctx.tiers.start
  return ctx.gray.run(tier, signal, s => loadTier(ctx, 'gray', tier, s, true))
}

/**
 * After a context restore: the start tier first (whole, so the globe has its
 * gray again after one decode from cache), then the highest tier asked for.
 */
export async function restoreGray(ctx: BasemapContext, signal: AbortSignal): Promise<void> {
  await loadStartGray(ctx, signal)
  const wanted = ctx.gray.wanted
  if (wanted !== null && tierRank(wanted) > tierRank(ctx.tiers.start)) await upgradeGray(ctx, signal)
}

/** Background: the gray at the maximum tier (a no-op when the start tier is the maximum). */
export function upgradeGray(ctx: BasemapContext, signal: AbortSignal): Promise<void> {
  const tier = ctx.tiers.max
  return ctx.gray.run(tier, signal, s => loadTier(ctx, 'gray', tier, s))
}

/** Background or on request: the satellite at `tier`. */
export function loadSatellite(ctx: BasemapContext, tier: BasemapTier, signal: AbortSignal): Promise<void> {
  return ctx.satellite.run(tier, signal, s => loadTier(ctx, 'satellite', tier, s))
}

/**
 * `webglcontextlost`. After the restore three re-uploads every texture from
 * its `image` at the next render: a strip-built texture would be reallocated
 * empty (black, up to 683 MiB at 16k) and a closed bitmap fails with
 * INVALID_VALUE, and every basemap bitmap is closed. The first render after a
 * restore can come from a listener that runs before ours (sceneInit restarts
 * the loop synchronously), so everything is put right here, while the context
 * is lost: pure JS, no GL call. Running loads are aborted and handed over;
 * both basemaps are dropped until the restore loads them again.
 *
 * onSatelliteTexture(false) reports only that the texture is gone: the shader
 * shows the gray until the restore commits a satellite again. The active
 * satellite (Mapbox's style, the dot colours) does not depend on this canvas
 * and stays on; only a failed reload after the restore ends it (useTextureLoading).
 */
export function releaseOnContextLost(ctx: BasemapContext): void {
  const reason = new Error('basemap: WebGL context lost')
  ctx.gray.abortAll(reason)
  ctx.satellite.abortAll(reason)
  swapUniform(ctx.materials, 'uGrayBasemap', null)
  ctx.gray.tier = null
  ctx.gray.texture = null
  swapUniform(ctx.materials, 'uSatellite', null)
  ctx.satellite.tier = null
  ctx.satellite.texture = null
  ctx.onSatelliteTexture(false)
}

/**
 * `webglcontextrestored`: aborts what was started while the context was lost
 * (its uploads went nowhere; loadTier does not commit them) and names what the
 * caller must request again.
 */
export function reloadAfterContextRestored(ctx: BasemapContext): { gray: boolean; satellite: boolean } {
  const reason = new Error('basemap: WebGL context restored')
  ctx.gray.abortAll(reason)
  ctx.satellite.abortAll(reason)
  return { gray: ctx.gray.wanted !== null, satellite: ctx.satellite.wanted !== null }
}

/** Unmount: aborts every load and frees every texture this context owns (their bitmaps are closed already). */
export function disposeBasemaps(ctx: BasemapContext): void {
  const reason = new Error('basemap: globe unmounted')
  ctx.gray.abortAll(reason)
  ctx.satellite.abortAll(reason)
  swapUniform(ctx.materials, 'uGrayBasemap', null)
  swapUniform(ctx.materials, 'uSatellite', null)
  ctx.gray.texture = null
  ctx.gray.tier = null
  ctx.satellite.texture = null
  ctx.satellite.tier = null
}
