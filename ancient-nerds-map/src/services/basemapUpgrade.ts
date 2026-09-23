/**
 * Basemap textures: decode off the main thread, upload whole (start tier) or
 * in horizontal strips (everything from 8k up), swap into the basemap
 * materials, and come back after a WebGL context restore.
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
 *   frame after the mip copy.
 *
 * Plain `fetch`, not offlineFetch: today's <img> loads never failed in app
 * offline mode, and the service worker's basemap rule (src/pwa/runtimeCaching)
 * serves the offline download from the 'basemaps' cache.
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
 * silent GL error. One synchronous check per upload turns it into a failure
 * (the flag stays set until read, so a later check still sees it).
 */
function assertNoOutOfMemory(renderer: Uploader, what: string): void {
  const gl = renderer.getContext()
  if (gl.getError() === gl.OUT_OF_MEMORY) throw new Error(`${what}: GPU out of memory`)
}

/** Uploads a bitmap in one go (texStorage2D + texSubImage2D + mips) now, not inside the next render. */
export function uploadWhole(renderer: Uploader, bitmap: ImageBitmap): THREE.Texture<ImageBitmap> {
  const texture = new THREE.Texture(bitmap)
  configureBasemapTexture(texture)
  texture.needsUpdate = true
  renderer.initTexture(texture)
  assertNoOutOfMemory(renderer, `basemap upload ${bitmap.width}x${bitmap.height}`)
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

// ---------------------------------------------------------------------------
// Per-kind state and the loaders
// ---------------------------------------------------------------------------

/** What one basemap kind holds on the GPU, what is loading, and what was asked for. */
export class BasemapState {
  /** Tier of `texture`; null while none is committed. */
  tier: BasemapTier | null = null
  /** The texture the materials sample. */
  texture: THREE.Texture | null = null
  /** The whole-uploaded start texture whose bitmap stays open: three re-uploads it after a context restore. */
  keeper: THREE.Texture<ImageBitmap> | null = null
  /** Highest tier ever asked for; a context restore asks for it again. */
  wanted: BasemapTier | null = null
  private flights = new Map<BasemapTier, { ctrl: AbortController; handedOver: boolean; done: Promise<void> }>()

  /** A texture of `tier` would raise what is held (never replace a higher tier with a lower one). */
  accepts(tier: BasemapTier): boolean {
    return this.tier === null || tierRank(tier) > tierRank(this.tier)
  }

  /**
   * Runs `load` for `tier` unless that tier or a higher one is held; a caller
   * asking for a tier that is already loading joins that load. The load's
   * signal aborts with the caller's signal (the promise rejects with its
   * reason) or with `abortAll` (the promise resolves: the context restore or
   * the unmount that cut it short owns what happens next, it is not a
   * failure of the load).
   */
  run(tier: BasemapTier, signal: AbortSignal, load: (signal: AbortSignal) => Promise<void>): Promise<void> {
    if (this.wanted === null || tierRank(tier) > tierRank(this.wanted)) this.wanted = tier
    if (!this.accepts(tier)) return Promise.resolve()
    const running = this.flights.get(tier)
    if (running) return running.done
    if (signal.aborted) return Promise.reject(signal.reason)
    const ctrl = new AbortController()
    const onAbort = () => ctrl.abort(signal.reason)
    signal.addEventListener('abort', onAbort, { once: true })
    const flight = { ctrl, handedOver: false, done: Promise.resolve() }
    flight.done = load(ctrl.signal)
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

  /** Aborts every running load of this kind; their callers' promises resolve (handed over). */
  abortAll(reason: unknown): void {
    this.flights.forEach(flight => {
      flight.handedOver = true
      flight.ctrl.abort(reason)
    })
    this.flights.clear()
  }
}

export interface BasemapContext {
  renderer: Uploader
  /** Every material with the basemap samplers: main, the four sections, back. */
  materials: THREE.ShaderMaterial[]
  tiers: { start: BasemapTier; max: BasemapTier }
  gray: BasemapState
  satellite: BasemapState
  nextFrame: (signal: AbortSignal) => Promise<void>
  onSatelliteReady: (ready: boolean) => void
}

/** Loads `tier` of `kind`, strips from med up, and commits it unless a higher tier landed meanwhile. */
async function loadTier(ctx: BasemapContext, kind: BasemapKind, tier: BasemapTier, signal: AbortSignal): Promise<void> {
  const bitmap = await decodeBasemap(getBasemapAssets(tier)[kind], signal)
  let texture: THREE.Texture
  if (tierRank(tier) >= tierRank('med')) {
    texture = await uploadInStrips(ctx.renderer, bitmap, { rows: STRIP_ROWS, nextFrame: ctx.nextFrame, signal })
  } else {
    try {
      texture = uploadWhole(ctx.renderer, bitmap)
    } finally {
      bitmap.close() // on the GPU now; a context restore drops this texture instead of re-uploading it
    }
  }
  const state = ctx[kind]
  if (!state.accepts(tier)) {
    texture.dispose()
    return
  }
  swapUniform(ctx.materials, UNIFORM[kind], texture)
  state.tier = tier
  state.texture = texture
  if (kind === 'satellite') ctx.onSatelliteReady(true)
}

/**
 * The critical-path gray: the start tier, uploaded whole before the first
 * render needs it, assigned only once it is on the GPU. Its bitmap stays open
 * so a context restore can bring it back without a network round trip.
 */
export async function loadStartGray(ctx: BasemapContext, signal: AbortSignal): Promise<void> {
  const bitmap = await decodeBasemap(getBasemapAssets(ctx.tiers.start).gray, signal)
  let texture: THREE.Texture<ImageBitmap>
  try {
    texture = uploadWhole(ctx.renderer, bitmap)
  } catch (err) {
    bitmap.close()
    throw err
  }
  swapUniform(ctx.materials, 'uGrayBasemap', texture)
  ctx.gray.tier = ctx.tiers.start
  ctx.gray.texture = texture
  ctx.gray.keeper = texture
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
 * After `webglcontextrestored` three re-uploads every texture from its
 * `image`: the kept start gray comes back from its open bitmap, strip-built
 * textures would come back empty (black) and closed bitmaps not at all. So the
 * gray returns to the start tier, the satellite is dropped, running loads are
 * aborted, and the caller re-requests what this returns.
 */
export function restoreAfterContextLoss(ctx: BasemapContext): { grayUpgrade: boolean; satellite: boolean } {
  const reason = new Error('basemap: WebGL context restored')
  ctx.gray.abortAll(reason)
  ctx.satellite.abortAll(reason)

  const keeper = ctx.gray.keeper
  if (keeper) {
    ctx.renderer.initTexture(keeper) // re-upload from the open bitmap before any material samples it
    swapUniform(ctx.materials, 'uGrayBasemap', keeper)
    ctx.gray.tier = ctx.tiers.start
    ctx.gray.texture = keeper
  }
  if (ctx.satellite.texture) swapUniform(ctx.materials, 'uSatellite', null)
  ctx.satellite.tier = null
  ctx.satellite.texture = null
  ctx.onSatelliteReady(false)

  const grayWanted = ctx.gray.wanted
  return {
    grayUpgrade: grayWanted !== null && tierRank(grayWanted) > tierRank(ctx.tiers.start),
    satellite: ctx.satellite.wanted !== null,
  }
}

/** Unmount: aborts every load and frees every texture and bitmap this context owns. */
export function disposeBasemaps(ctx: BasemapContext): void {
  const reason = new Error('basemap: globe unmounted')
  ctx.gray.abortAll(reason)
  ctx.satellite.abortAll(reason)
  swapUniform(ctx.materials, 'uGrayBasemap', null)
  swapUniform(ctx.materials, 'uSatellite', null)
  const keeper = ctx.gray.keeper
  if (keeper) {
    keeper.dispose()
    keeper.image.close()
  }
  ctx.gray.keeper = null
  ctx.gray.texture = null
  ctx.gray.tier = null
  ctx.satellite.texture = null
  ctx.satellite.tier = null
}
