/**
 * The basemap upload paths against a duck-typed renderer. What they must do in
 * three r182 is derived in the texture brief (§3, with the orientation of its
 * option B) and proven against a real WebGL2 context in
 * scripts/globe_probe/strip_upload_check.py; here the call sequence and the
 * texture state at every call are pinned.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as THREE from 'three'
import {
  BasemapState,
  disposeBasemaps,
  decodeBasemap,
  loadSatellite,
  loadStartGray,
  nextAnimationFrame,
  restoreAfterContextLoss,
  STRIP_ROWS,
  stripPlan,
  swapUniform,
  upgradeGray,
  uploadInStrips,
  uploadWhole,
  type BasemapContext,
  type Uploader,
} from '../basemapUpgrade'

const OOM = 0x0505

interface FakeBitmap { width: number; height: number; close: ReturnType<typeof vi.fn> }

function fakeBitmap(width = 16383, height = 8192): FakeBitmap {
  return { width, height, close: vi.fn() }
}

interface CopyCall {
  src: THREE.Texture
  dst: THREE.Texture
  box: { minX: number; minY: number; maxX: number; maxY: number }
  at: { x: number; y: number }
  srcLevel: number | undefined
  dstLevel: number | undefined
  generateMipmaps: boolean
  dstVersion: number
}

function fakeRenderer(opts: { errorAfter?: (n: number) => number } = {}) {
  const log: string[] = []
  const copies: CopyCall[] = []
  const initSnapshots: Array<Record<string, unknown>> = []
  const initialised: THREE.Texture[] = []
  let errorCalls = 0
  const renderer = {
    initTexture: vi.fn((t: THREE.Texture) => {
      log.push('init')
      initialised.push(t)
      const img = t.image as { width: number; height: number }
      initSnapshots.push({
        generateMipmaps: t.generateMipmaps,
        dataReady: t.source.dataReady,
        version: t.version,
        width: img.width,
        height: img.height,
        colorSpace: t.colorSpace,
        flipY: t.flipY,
        premultiplyAlpha: t.premultiplyAlpha,
        minFilter: t.minFilter,
        magFilter: t.magFilter,
        anisotropy: t.anisotropy,
        mipmaps: (t.mipmaps ?? []).map(m => [(m as { width: number }).width, (m as { height: number }).height]),
      })
    }),
    copyTextureToTexture: vi.fn((src: THREE.Texture, dst: THREE.Texture, box: THREE.Box2, at: THREE.Vector2, srcLevel?: number, dstLevel?: number) => {
      log.push('copy')
      copies.push({
        src, dst,
        box: { minX: box.min.x, minY: box.min.y, maxX: box.max.x, maxY: box.max.y },
        at: { x: at.x, y: at.y },
        srcLevel, dstLevel,
        generateMipmaps: dst.generateMipmaps,
        dstVersion: dst.version,
      })
    }),
    getContext: vi.fn(() => ({
      OUT_OF_MEMORY: OOM,
      getError: () => {
        errorCalls += 1
        log.push('getError')
        return opts.errorAfter ? opts.errorAfter(errorCalls) : 0
      },
    })),
  }
  return { renderer: renderer as unknown as Uploader & typeof renderer, log, copies, initSnapshots, initialised }
}

/** A nextFrame that records itself in the log and resolves at once (or rejects when aborted). */
function frames(log: string[]) {
  return vi.fn(async (signal: AbortSignal) => {
    if (signal.aborted) throw signal.reason
    log.push('frame')
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('stripPlan', () => {
  it('cuts 16383x8192 into 32 contiguous 256-row strips', () => {
    const plan = stripPlan(16383, 8192, 256)
    expect(plan).toHaveLength(32)
    let y = 0
    plan.forEach((s, i) => {
      expect(s.y).toBe(y)
      expect(s.h).toBe(256)
      expect(s.last).toBe(i === plan.length - 1)
      y += s.h
    })
    expect(y).toBe(8192)
  })

  it('gives the remainder to the last strip', () => {
    const plan = stripPlan(100, 1000, 256)
    expect(plan.map(s => [s.y, s.h])).toEqual([[0, 256], [256, 256], [512, 256], [768, 232]])
    expect(plan.filter(s => s.last)).toHaveLength(1)
  })
})

describe('decodeBasemap', () => {
  it('rejects on an HTTP error with the URL and the status, without decoding', async () => {
    const createImageBitmap = vi.fn()
    vi.stubGlobal('createImageBitmap', createImageBitmap)
    vi.stubGlobal('fetch', vi.fn(async () => new Response('nope', { status: 404 })))
    await expect(decodeBasemap('/data/basemaps/gray_dark_med.webp', new AbortController().signal))
      .rejects.toThrow(/\/data\/basemaps\/gray_dark_med\.webp.*404/)
    expect(createImageBitmap).not.toHaveBeenCalled()
  })

  it('decodes off the main thread with the default options (each option costs main-thread time in Chrome)', async () => {
    const bitmap = fakeBitmap(8192, 4096)
    const createImageBitmap = vi.fn(async () => bitmap)
    const fetchMock = vi.fn(async () => new Response(new Blob([new Uint8Array([1, 2, 3])], { type: 'image/webp' })))
    vi.stubGlobal('createImageBitmap', createImageBitmap)
    vi.stubGlobal('fetch', fetchMock)
    const ctrl = new AbortController()
    await expect(decodeBasemap('/data/basemaps/satellite_med.webp', ctrl.signal)).resolves.toBe(bitmap)
    expect(fetchMock).toHaveBeenCalledWith('/data/basemaps/satellite_med.webp', { signal: ctrl.signal })
    expect(createImageBitmap).toHaveBeenCalledTimes(1)
    const args = createImageBitmap.mock.calls[0] as unknown as unknown[]
    expect(args).toHaveLength(1)
    expect(args[0]).toBeInstanceOf(Blob)
  })

  it('closes a bitmap that arrives after the abort and rejects with the abort reason', async () => {
    const bitmap = fakeBitmap()
    const ctrl = new AbortController()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new Blob([new Uint8Array([1])]))))
    vi.stubGlobal('createImageBitmap', vi.fn(async () => { ctrl.abort(new Error('unmounted')); return bitmap }))
    await expect(decodeBasemap('/x.webp', ctrl.signal)).rejects.toThrow('unmounted')
    expect(bitmap.close).toHaveBeenCalledTimes(1)
  })
})

describe('uploadWhole', () => {
  it('uploads before any render, with the settings of the old <img> path', () => {
    const { renderer, initSnapshots, initialised } = fakeRenderer()
    const bitmap = fakeBitmap(8192, 4096)
    const tex = uploadWhole(renderer, bitmap as unknown as ImageBitmap)
    expect(initialised).toEqual([tex])
    expect(tex.image).toBe(bitmap)
    expect(initSnapshots[0]).toMatchObject({
      generateMipmaps: true, dataReady: true, version: 1, width: 8192, height: 4096,
      colorSpace: THREE.SRGBColorSpace, flipY: false, premultiplyAlpha: false,
      minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter, anisotropy: 16,
    })
    expect(bitmap.close).not.toHaveBeenCalled()
  })

  it('fails explicitly when the GPU runs out of memory', () => {
    const { renderer } = fakeRenderer({ errorAfter: () => OOM })
    expect(() => uploadWhole(renderer, fakeBitmap() as unknown as ImageBitmap)).toThrow(/out of memory/)
  })
})

describe('uploadInStrips', () => {
  async function run(width = 16383, height = 8192) {
    const r = fakeRenderer()
    const bitmap = fakeBitmap(width, height)
    bitmap.close.mockImplementation(() => { r.log.push('close') })
    const nextFrame = frames(r.log)
    const tex = await uploadInStrips(r.renderer, bitmap as unknown as ImageBitmap, { rows: 256, nextFrame, signal: new AbortController().signal })
    return { ...r, bitmap, tex, nextFrame }
  }

  it('allocates once from the bitmap size: the full mip chain from a size list, no data, no mip pass', async () => {
    const { initSnapshots, initialised, log, tex } = await run()
    expect(initialised).toEqual([tex])
    expect(log.indexOf('init')).toBeLessThan(log.indexOf('copy'))
    expect(initSnapshots[0]).toMatchObject({
      generateMipmaps: false, dataReady: false, version: 1, width: 16383, height: 8192,
      colorSpace: THREE.SRGBColorSpace, flipY: false, premultiplyAlpha: false,
      minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter, anisotropy: 16,
    })
    // 14 levels for 16383x8192 (floor(log2 16383) + 1), each floor-halved like GL does
    const mips = initSnapshots[0].mipmaps as number[][]
    expect(mips).toHaveLength(14)
    expect(mips[0]).toEqual([16383, 8192])
    expect(mips[1]).toEqual([8191, 4096])
    expect(mips[13]).toEqual([1, 1])
  })

  it('suppresses mipmaps on every strip and generates them once on the final copy', async () => {
    const { copies } = await run()
    const plan = stripPlan(16383, 8192, 256)
    expect(copies).toHaveLength(plan.length + 1)
    expect(copies.slice(0, -1).every(c => c.generateMipmaps === false)).toBe(true)
    expect(copies[copies.length - 1].generateMipmaps).toBe(true)
  })

  it('copies from one never-uploaded source texture, strip by strip, level 0 to level 0', async () => {
    const { copies, initialised, bitmap, tex } = await run()
    const src = copies[0].src
    expect(src.image).toBe(bitmap)
    expect(copies.every(c => c.src === src && c.dst === tex)).toBe(true)
    expect(initialised).not.toContain(src)
    expect(copies.every(c => c.srcLevel === 0 && c.dstLevel === 0)).toBe(true)
    // the texture version is never bumped after the allocation (a bump would reallocate and lose the strips)
    expect(copies.every(c => c.dstVersion === 1)).toBe(true)
    const plan = stripPlan(16383, 8192, 256)
    plan.forEach((s, i) => {
      expect(copies[i].box).toEqual({ minX: 0, minY: s.y, maxX: 16383, maxY: s.y + s.h })
      expect(copies[i].at).toEqual({ x: 0, y: s.y })
    })
    expect(copies[plan.length].box).toEqual({ minX: 0, minY: 8191, maxX: 16383, maxY: 8192 })
    expect(copies[plan.length].at).toEqual({ x: 0, y: 8191 })
  })

  it('waits one frame after every copy', async () => {
    const { log } = await run(100, 600)
    const seq = log.filter(e => e === 'copy' || e === 'frame')
    expect(seq).toEqual(['copy', 'frame', 'copy', 'frame', 'copy', 'frame', 'copy', 'frame'])
  })

  it('checks for GL out-of-memory once, a frame after the mipmaps, and closes the bitmap last', async () => {
    const { log, tex } = await run(100, 600)
    expect(log).toEqual(['init', 'copy', 'frame', 'copy', 'frame', 'copy', 'frame', 'copy', 'frame', 'getError', 'close'])
    // back at the allocation-time value, which is part of three's texture cache key
    expect(tex.generateMipmaps).toBe(false)
  })

  it('stops at an abort: no further copies, destination disposed, bitmap closed, uniforms untouched', async () => {
    const r = fakeRenderer()
    const bitmap = fakeBitmap(100, 1000)
    const ctrl = new AbortController()
    const material = new THREE.ShaderMaterial({ uniforms: { uGrayBasemap: { value: 'old' } } })
    let n = 0
    const nextFrame = vi.fn(async (signal: AbortSignal) => {
      n += 1
      if (n === 2) ctrl.abort(new Error('toggled off'))
      if (signal.aborted) throw signal.reason
    })
    const disposeSpy = vi.spyOn(THREE.Texture.prototype, 'dispose')
    await expect(uploadInStrips(r.renderer, bitmap as unknown as ImageBitmap, { rows: 256, nextFrame, signal: ctrl.signal }))
      .rejects.toThrow('toggled off')
    expect(r.copies).toHaveLength(2)
    expect(disposeSpy).toHaveBeenCalledTimes(1)
    expect(disposeSpy.mock.contexts[0]).toBe(r.copies[0].dst)
    expect(bitmap.close).toHaveBeenCalledTimes(1)
    expect(material.uniforms.uGrayBasemap.value).toBe('old')
  })

  it('fails the upload on GL out-of-memory: destination disposed, bitmap closed, nothing returned', async () => {
    const r = fakeRenderer({ errorAfter: () => OOM })
    const bitmap = fakeBitmap(100, 600)
    const disposeSpy = vi.spyOn(THREE.Texture.prototype, 'dispose')
    await expect(uploadInStrips(r.renderer, bitmap as unknown as ImageBitmap, { rows: 256, nextFrame: frames(r.log), signal: new AbortController().signal }))
      .rejects.toThrow(/out of memory/)
    expect(disposeSpy).toHaveBeenCalledTimes(1)
    expect(disposeSpy.mock.contexts[0]).toBe(r.copies[0].dst)
    expect(bitmap.close).toHaveBeenCalledTimes(1)
  })
})

describe('swapUniform', () => {
  it('points every material at the new texture before it disposes the old one', () => {
    const old = new THREE.Texture()
    const next = new THREE.Texture()
    const materials = Array.from({ length: 6 }, () => new THREE.ShaderMaterial({ uniforms: { uGrayBasemap: { value: old } } }))
    const seen: Array<unknown[]> = []
    old.dispose = vi.fn(() => { seen.push(materials.map(m => m.uniforms.uGrayBasemap.value)) })
    swapUniform(materials, 'uGrayBasemap', next)
    expect(old.dispose).toHaveBeenCalledTimes(1)
    expect(seen[0].every(v => v === next)).toBe(true)
  })

  it('disposes nothing when there was no texture or it is the same one', () => {
    const tex = new THREE.Texture()
    tex.dispose = vi.fn()
    const materials = [new THREE.ShaderMaterial({ uniforms: { uSatellite: { value: null } } })]
    swapUniform(materials, 'uSatellite', tex)
    swapUniform(materials, 'uSatellite', tex)
    expect(tex.dispose).not.toHaveBeenCalled()
    expect(materials[0].uniforms.uSatellite.value).toBe(tex)
  })
})

describe('nextAnimationFrame', () => {
  beforeEach(() => {
    let id = 0
    const pending = new Map<number, FrameRequestCallback>()
    vi.stubGlobal('requestAnimationFrame', vi.fn((cb: FrameRequestCallback) => { id += 1; pending.set(id, cb); return id }))
    vi.stubGlobal('cancelAnimationFrame', vi.fn((i: number) => { pending.delete(i) }))
    ;(globalThis as { __frames?: Map<number, FrameRequestCallback> }).__frames = pending
  })

  it('resolves on the next frame', async () => {
    const p = nextAnimationFrame(new AbortController().signal)
    const pending = (globalThis as { __frames?: Map<number, FrameRequestCallback> }).__frames!
    ;[...pending.values()].forEach(cb => cb(0))
    await expect(p).resolves.toBeUndefined()
  })

  it('rejects with the abort reason and cancels the frame (a hidden tab never delivers one)', async () => {
    const ctrl = new AbortController()
    const p = nextAnimationFrame(ctrl.signal)
    ctrl.abort(new Error('gone'))
    await expect(p).rejects.toThrow('gone')
    expect(cancelAnimationFrame).toHaveBeenCalledWith(1)
  })

  it('rejects at once when already aborted', async () => {
    const ctrl = new AbortController()
    ctrl.abort(new Error('before'))
    await expect(nextAnimationFrame(ctrl.signal)).rejects.toThrow('before')
    expect(requestAnimationFrame).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// The per-kind loaders over a context
// ---------------------------------------------------------------------------

interface Deferred<T> { promise: Promise<T>; resolve: (v: T) => void }
function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}

/** fetch + createImageBitmap stubs; each URL's decode resolves when the test says so. */
function stubDecoding(sizes: Record<string, [number, number]>) {
  const gates = new Map<string, Deferred<void>>()
  const bitmaps = new Map<string, FakeBitmap>()
  const fetched: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    fetched.push(url)
    return new Response(new Blob([url]))
  }))
  vi.stubGlobal('createImageBitmap', vi.fn(async (blob: Blob) => {
    const url = await blob.text()
    const gate = gates.get(url)
    if (gate) await gate.promise
    const [w, h] = sizes[url]
    const bmp = fakeBitmap(w, h)
    bitmaps.set(url, bmp)
    return bmp
  }))
  return {
    fetched,
    bitmaps,
    hold(url: string) { const d = deferred<void>(); gates.set(url, d); return () => d.resolve() },
  }
}

const SIZES: Record<string, [number, number]> = {
  '/data/basemaps/gray_dark_low.webp': [4096, 2048],
  '/data/basemaps/gray_dark_med.webp': [8192, 4096],
  '/data/basemaps/gray_dark_high.webp': [16383, 8192],
  '/data/basemaps/satellite_low.webp': [4096, 2048],
  '/data/basemaps/satellite_med.webp': [8192, 4096],
  '/data/basemaps/satellite_high.webp': [16383, 8192],
}

function makeCtx(tiers: BasemapContext['tiers'] = { start: 'med', max: 'high' }) {
  const r = fakeRenderer()
  const materials = Array.from({ length: 6 }, () => new THREE.ShaderMaterial({
    uniforms: { uGrayBasemap: { value: null }, uSatellite: { value: null } },
  }))
  const onSatelliteReady = vi.fn()
  const ctx: BasemapContext = {
    renderer: r.renderer,
    materials,
    tiers,
    gray: new BasemapState(),
    satellite: new BasemapState(),
    nextFrame: frames(r.log),
    onSatelliteReady,
  }
  return { ctx, ...r, materials, onSatelliteReady }
}

const uniformOf = (ctx: BasemapContext, name: 'uGrayBasemap' | 'uSatellite') =>
  ctx.materials.map(m => m.uniforms[name].value as THREE.Texture | null)

describe('loadStartGray', () => {
  it('uploads the start-tier gray whole, before assigning it, and keeps its bitmap for a context restore', async () => {
    const dec = stubDecoding(SIZES)
    const { ctx, log } = makeCtx({ start: 'med', max: 'high' })
    let assignedBeforeInit = false
    const origInit = ctx.renderer.initTexture
    ctx.renderer.initTexture = vi.fn((t: THREE.Texture) => {
      assignedBeforeInit = uniformOf(ctx, 'uGrayBasemap').some(v => v === t)
      origInit(t)
    }) as Uploader['initTexture']
    await loadStartGray(ctx, new AbortController().signal)
    expect(dec.fetched).toEqual(['/data/basemaps/gray_dark_med.webp'])
    expect(assignedBeforeInit).toBe(false)
    const tex = uniformOf(ctx, 'uGrayBasemap')[0]!
    expect(uniformOf(ctx, 'uGrayBasemap').every(v => v === tex)).toBe(true)
    expect(ctx.gray.tier).toBe('med')
    expect(ctx.gray.texture).toBe(tex)
    expect(ctx.gray.keeper).toBe(tex)
    expect(dec.bitmaps.get('/data/basemaps/gray_dark_med.webp')!.close).not.toHaveBeenCalled()
    expect(log).not.toContain('copy')
  })
})

describe('upgradeGray', () => {
  it('replaces the start tier with the maximum tier through the strip path', async () => {
    const dec = stubDecoding(SIZES)
    const { ctx, copies } = makeCtx({ start: 'med', max: 'high' })
    await loadStartGray(ctx, new AbortController().signal)
    const start = ctx.gray.texture!
    const disposeStart = vi.spyOn(start, 'dispose')
    await upgradeGray(ctx, new AbortController().signal)
    expect(dec.fetched).toEqual(['/data/basemaps/gray_dark_med.webp', '/data/basemaps/gray_dark_high.webp'])
    const high = ctx.gray.texture!
    expect(high).not.toBe(start)
    expect(copies.length).toBe(stripPlan(16383, 8192, STRIP_ROWS).length + 1)
    expect(uniformOf(ctx, 'uGrayBasemap').every(v => v === high)).toBe(true)
    expect(ctx.gray.tier).toBe('high')
    // GPU copy of the start tier is freed; its bitmap stays for a context restore
    expect(disposeStart).toHaveBeenCalledTimes(1)
    expect(dec.bitmaps.get('/data/basemaps/gray_dark_med.webp')!.close).not.toHaveBeenCalled()
    expect(ctx.gray.keeper).toBe(start)
  })

  it('does nothing when the start tier is the maximum', async () => {
    const dec = stubDecoding(SIZES)
    const { ctx } = makeCtx({ start: 'med', max: 'med' })
    await loadStartGray(ctx, new AbortController().signal)
    await upgradeGray(ctx, new AbortController().signal)
    expect(dec.fetched).toEqual(['/data/basemaps/gray_dark_med.webp'])
  })
})

describe('loadSatellite', () => {
  it('uses the strip path from med up and publishes readiness after the swap', async () => {
    stubDecoding(SIZES)
    const { ctx, copies, onSatelliteReady } = makeCtx({ start: 'med', max: 'high' })
    onSatelliteReady.mockImplementation(() => {
      expect(uniformOf(ctx, 'uSatellite').every(v => v === ctx.satellite.texture)).toBe(true)
    })
    await loadSatellite(ctx, 'med', new AbortController().signal)
    expect(copies.length).toBe(stripPlan(8192, 4096, STRIP_ROWS).length + 1)
    expect(onSatelliteReady).toHaveBeenCalledWith(true)
    expect(ctx.satellite.tier).toBe('med')
  })

  it('uploads the low tier whole and closes its bitmap', async () => {
    const dec = stubDecoding(SIZES)
    const { ctx, copies, initialised } = makeCtx({ start: 'low', max: 'med' })
    await loadSatellite(ctx, 'low', new AbortController().signal)
    expect(copies).toHaveLength(0)
    expect(initialised).toEqual([ctx.satellite.texture])
    expect(dec.bitmaps.get('/data/basemaps/satellite_low.webp')!.close).toHaveBeenCalledTimes(1)
  })

  it('joins a load of the same tier that is already running', async () => {
    const dec = stubDecoding(SIZES)
    const release = dec.hold('/data/basemaps/satellite_med.webp')
    const { ctx } = makeCtx()
    const a = loadSatellite(ctx, 'med', new AbortController().signal)
    const b = loadSatellite(ctx, 'med', new AbortController().signal)
    release()
    await Promise.all([a, b])
    expect(dec.fetched).toEqual(['/data/basemaps/satellite_med.webp'])
  })

  it('never replaces a higher tier with a lower one that arrives later', async () => {
    const dec = stubDecoding(SIZES)
    const releaseMed = dec.hold('/data/basemaps/satellite_med.webp')
    const { ctx } = makeCtx({ start: 'med', max: 'high' })
    const med = loadSatellite(ctx, 'med', new AbortController().signal)
    await loadSatellite(ctx, 'high', new AbortController().signal)
    const high = ctx.satellite.texture!
    const disposeSpy = vi.spyOn(THREE.Texture.prototype, 'dispose')
    releaseMed()
    await med
    expect(ctx.satellite.tier).toBe('high')
    expect(ctx.satellite.texture).toBe(high)
    expect(uniformOf(ctx, 'uSatellite').every(v => v === high)).toBe(true)
    // the late med texture was built and thrown away
    expect(disposeSpy).toHaveBeenCalledTimes(1)
    expect(disposeSpy.mock.contexts[0]).not.toBe(high)
    // and a request for a tier already held does not fetch at all
    await loadSatellite(ctx, 'med', new AbortController().signal)
    expect(dec.fetched.filter(u => u.includes('satellite_med'))).toHaveLength(1)
  })

  it('aborting one tier leaves the uniforms and the held texture alone', async () => {
    stubDecoding(SIZES)
    const { ctx } = makeCtx({ start: 'med', max: 'high' })
    await loadSatellite(ctx, 'med', new AbortController().signal)
    const med = ctx.satellite.texture
    const ctrl = new AbortController()
    ctx.nextFrame = vi.fn(async (signal: AbortSignal) => { ctrl.abort(new Error('off')); if (signal.aborted) throw signal.reason })
    await expect(loadSatellite(ctx, 'high', ctrl.signal)).rejects.toThrow('off')
    expect(ctx.satellite.texture).toBe(med)
    expect(uniformOf(ctx, 'uSatellite').every(v => v === med)).toBe(true)
  })
})

describe('disposeBasemaps', () => {
  it('aborts running loads, frees every texture, closes the kept bitmap and clears the uniforms', async () => {
    const dec = stubDecoding(SIZES)
    const { ctx } = makeCtx({ start: 'med', max: 'high' })
    await loadStartGray(ctx, new AbortController().signal)
    await loadSatellite(ctx, 'med', new AbortController().signal)
    const release = dec.hold('/data/basemaps/gray_dark_high.webp')
    const upgrading = upgradeGray(ctx, new AbortController().signal)
    const gray = ctx.gray.texture!
    const sat = ctx.satellite.texture!
    const disposeGray = vi.spyOn(gray, 'dispose')
    const disposeSat = vi.spyOn(sat, 'dispose')

    disposeBasemaps(ctx)
    release()

    await expect(upgrading).rejects.toThrow(/unmounted/)
    expect(disposeGray).toHaveBeenCalled()
    expect(disposeSat).toHaveBeenCalled()
    expect(dec.bitmaps.get('/data/basemaps/gray_dark_med.webp')!.close).toHaveBeenCalledTimes(1)
    expect(dec.bitmaps.get('/data/basemaps/gray_dark_high.webp')!.close).toHaveBeenCalledTimes(1)
    expect(uniformOf(ctx, 'uGrayBasemap').every(v => v === null)).toBe(true)
    expect(uniformOf(ctx, 'uSatellite').every(v => v === null)).toBe(true)
    expect(ctx.gray.keeper).toBe(null)
  })
})

describe('restoreAfterContextLoss', () => {
  it('points the gray back at the kept start texture, drops strip-built textures, and names the upgrades to redo', async () => {
    stubDecoding(SIZES)
    const { ctx, initialised } = makeCtx({ start: 'med', max: 'high' })
    await loadStartGray(ctx, new AbortController().signal)
    const start = ctx.gray.keeper!
    await upgradeGray(ctx, new AbortController().signal)
    await loadSatellite(ctx, 'med', new AbortController().signal)
    const high = ctx.gray.texture!
    const sat = ctx.satellite.texture!
    const disposeHigh = vi.spyOn(high, 'dispose')
    const disposeSat = vi.spyOn(sat, 'dispose')
    const before = initialised.length

    const redo = restoreAfterContextLoss(ctx)

    expect(redo).toEqual({ grayUpgrade: true, satellite: true })
    expect(initialised.slice(before)).toEqual([start])
    expect(uniformOf(ctx, 'uGrayBasemap').every(v => v === start)).toBe(true)
    expect(uniformOf(ctx, 'uSatellite').every(v => v === null)).toBe(true)
    expect(disposeHigh).toHaveBeenCalledTimes(1)
    expect(disposeSat).toHaveBeenCalledTimes(1)
    expect(ctx.gray.tier).toBe('med')
    expect(ctx.satellite.tier).toBe(null)
    expect(ctx.onSatelliteReady).toHaveBeenLastCalledWith(false)
  })

  it('asks for nothing that was never asked for', async () => {
    stubDecoding(SIZES)
    const { ctx } = makeCtx({ start: 'med', max: 'high' })
    await loadStartGray(ctx, new AbortController().signal)
    expect(restoreAfterContextLoss(ctx)).toEqual({ grayUpgrade: false, satellite: false })
  })

  it('aborts uploads that were running when the context came back', async () => {
    const dec = stubDecoding(SIZES)
    const release = dec.hold('/data/basemaps/satellite_med.webp')
    const { ctx } = makeCtx({ start: 'med', max: 'high' })
    await loadStartGray(ctx, new AbortController().signal)
    const running = loadSatellite(ctx, 'med', new AbortController().signal)
    const redo = restoreAfterContextLoss(ctx)
    release()
    await expect(running).rejects.toThrow(/context restored/)
    expect(redo.satellite).toBe(true)
    expect(ctx.satellite.texture).toBe(null)
    expect(dec.bitmaps.get('/data/basemaps/satellite_med.webp')!.close).toHaveBeenCalledTimes(1)
  })
})
