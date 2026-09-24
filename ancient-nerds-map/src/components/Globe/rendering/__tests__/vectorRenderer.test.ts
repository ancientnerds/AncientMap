/**
 * The vector layer loader: one fetch and one worker parse per layer file, front and back built
 * from the same result in one synchronous commit, background tiers swapped in place, and every
 * failure surfaced exactly once. Runs in node: three's objects construct without WebGL, the
 * worker is replaced by the same pure function it runs (processLayerRequest), and OfflineFetch
 * falls through to the stubbed fetch because node has no Cache API.
 */

import * as THREE from 'three'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../../utils/LabelRenderer', async () => {
  const three = await import('three')
  return {
    createLabelTexture: vi.fn(() => ({ texture: new three.Texture(), width: 100, height: 20 })),
    createGlobeTangentLabel: vi.fn(() => new three.Mesh()),
  }
})

import manifest from '../../../../data/globeLayers.generated.json'
import { createGlobeLayerTiers, getLayerFiles, getLayerUrl, type GlobeLayerKey, type VectorLayerKey } from '../../../../config/vectorLayers'
import { OfflineFetch, OfflineNotCachedError } from '../../../../services/OfflineFetch'
import type { FadeManager } from '../../../../utils/FadeManager'
import type { GlobeLabel } from '../vectorRenderer'
import {
  _resetParsedLayerCacheForTests,
  createLayerParser,
  ensureHiresCoastline,
  fetchLayerBuffer,
  loadVectorLayer,
  pickLayersToLoad,
  preloadRiversLakes,
  resumeDeferredGlobeLayers,
  upgradeGlobeLayers,
  upgradeLayerTier,
  type ParseLayer,
  type VectorRendererContext,
} from '../vectorRenderer'
import { processLayerRequest, type LayerWorkerRequest, type LayerWorkerResponse } from '../segmentBuilder'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

type Body = { status?: number; features?: unknown[] }

/** A FeatureCollection with n two-point lines, so each tier has a distinct vertex count. */
function lines(n: number, named = false): unknown[] {
  return Array.from({ length: n }, (_, i) => ({
    type: 'Feature',
    properties: named ? { name: `L${i}` } : {},
    geometry: { type: 'LineString', coordinates: [[i, 10], [i + 0.5, 10.5]] },
  }))
}

/** A held fetch answers once released; a release before the request arrives lets it through. */
interface Gate { released: boolean; go?: () => void }

let routes: Map<string, Body>
let fetched: string[]
let held: Map<string, Gate>

function respond(url: string): Response {
  const body = routes.get(url)
  if (!body) return new Response('<!doctype html>', { status: 404 })
  return new Response(JSON.stringify({ type: 'FeatureCollection', features: body.features ?? [] }), { status: body.status ?? 200 })
}

beforeEach(() => {
  routes = new Map()
  fetched = []
  held = new Map()
  _resetParsedLayerCacheForTests()
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    fetched.push(url)
    const signal = init?.signal
    if (signal?.aborted) return Promise.reject(new DOMException('aborted', 'AbortError'))
    return new Promise<Response>((resolve, reject) => {
      const onAbort = () => reject(new DOMException('aborted', 'AbortError'))
      signal?.addEventListener('abort', onAbort)
      const go = () => {
        signal?.removeEventListener('abort', onAbort)
        resolve(respond(url))
      }
      const gate = held.get(url)
      if (gate && !gate.released) gate.go = go
      else go()
    })
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/** Holds the fetch of `url` until the returned function is called. */
function hold(url: string): () => void {
  const gate: Gate = { released: false }
  held.set(url, gate)
  return () => { gate.released = true; gate.go?.() }
}

const inProcessParse: ParseLayer = async (buffer, radii, withLabels) => {
  const { response } = processLayerRequest({ id: 0, buffer, radii, withLabels })
  if ('error' in response) throw new Error(response.error)
  return { positions: response.positions, labels: response.labels }
}

function emptyLayers<T>(make: () => T): Record<VectorLayerKey, T> {
  return { coastlines: make(), countryBorders: make(), rivers: make(), lakes: make(), coralReefs: make(), glaciers: make(), plateBoundaries: make() }
}

function makeCtx(overrides: Partial<VectorRendererContext> = {}) {
  const globe = new THREE.Mesh()
  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera()
  camera.position.set(0, 0, 2.44)
  const loaded: Record<string, boolean> = {}
  const loading: Record<string, boolean> = {}
  const fade = vi.fn((_key: string, mats: THREE.Material[], target: number, opts?: { duration?: number; onComplete?: () => void }) => {
    mats.forEach(m => { (m as THREE.ShaderMaterial).uniforms.uOpacity.value = target })
    opts?.onComplete?.()
  })
  const abort = new AbortController()
  const ctx: VectorRendererContext = {
    sceneRef: { current: { renderer: {} as THREE.WebGLRenderer, scene, camera, controls: {}, points: null, backPoints: null, shadowPoints: null, globe } },
    shaderMaterialsRef: { current: [] },
    frontLineLayersRef: { current: emptyLayers<THREE.Line[]>(() => []) },
    backLineLayersRef: { current: emptyLayers<THREE.Line[]>(() => []) },
    fadeManagerRef: { current: { fadeTo: fade } as unknown as FadeManager },
    detailLevelRef: { current: 'ultra-low' },
    layerLabelsRef: { current: emptyLayers<GlobeLabel[]>(() => []) },
    allLabelMeshesRef: { current: [] },
    updateGeoLabelsRef: { current: null },
    vectorLayersRef: { current: { coastlines: true, countryBorders: true, rivers: true, lakes: true, coralReefs: false, glaciers: false, plateBoundaries: false } },
    satelliteModeRef: { current: false },
    layerLoadIdsRef: { current: {} },
    globeLayerTiersRef: { current: createGlobeLayerTiers() },
    failedLayersRef: { current: {} },
    setIsLoadingLayers: vi.fn(update => Object.assign(loading, typeof update === 'function' ? update({ ...loading }) : update)),
    setLayersLoaded: vi.fn(update => Object.assign(loaded, typeof update === 'function' ? update({ ...loaded }) : update)),
    parseLayer: vi.fn(inProcessParse),
    signal: abort.signal,
    onStartError: vi.fn(),
    ...overrides,
  }
  return { ctx, globe, scene, camera, loaded, loading, fade, abort }
}

function vertexRadius(line: THREE.Line): number {
  const attr = line.geometry.getAttribute('position')
  return Math.hypot(attr.getX(0), attr.getY(0), attr.getZ(0))
}

const COAST_START = manifest.coastlines.start
const COAST_DETAIL = manifest.coastlines.detail
const COAST_HIRES = '/data/layers/coast_hires.geojson'
const BORDERS_START = manifest.countryBorders.start
const BORDERS_DETAIL = manifest.countryBorders.detail

// ---------------------------------------------------------------------------
// Fetch
// ---------------------------------------------------------------------------

describe('fetchLayerBuffer', () => {
  it('throws with the URL and status when the response is not ok', async () => {
    await expect(fetchLayerBuffer('/data/layers/missing.json', new AbortController().signal))
      .rejects.toThrow('/data/layers/missing.json: HTTP 404')
  })
})

// ---------------------------------------------------------------------------
// First load
// ---------------------------------------------------------------------------

describe('loadVectorLayer', () => {
  it('fetches the start tier once and builds front and back from the one parse', async () => {
    routes.set(COAST_START, { features: lines(3) })
    const { ctx, globe, loaded } = makeCtx()
    let bothExistedWhenLoaded = false
    vi.mocked(ctx.setLayersLoaded).mockImplementation(update => {
      bothExistedWhenLoaded = ctx.frontLineLayersRef.current.coastlines.length === 1 && ctx.backLineLayersRef.current.coastlines.length === 1
      Object.assign(loaded, typeof update === 'function' ? update({}) : update)
    })

    await loadVectorLayer('coastlines', ctx)

    expect(fetched).toEqual([COAST_START])
    expect(ctx.parseLayer).toHaveBeenCalledTimes(1)
    const [front] = ctx.frontLineLayersRef.current.coastlines
    const [back] = ctx.backLineLayersRef.current.coastlines
    expect(front).toBeInstanceOf(THREE.LineSegments)
    expect(back).toBeInstanceOf(THREE.LineSegments)
    expect(vertexRadius(front)).toBeCloseTo(1.002, 6)
    expect(vertexRadius(back)).toBeCloseTo(1.001, 6)
    expect(front.renderOrder).toBe(10)
    expect(back.renderOrder).toBe(-10)
    expect(front.geometry.getAttribute('position').count).toBe(6)
    expect(globe.children).toEqual([front, back])
    expect(ctx.shaderMaterialsRef.current).toEqual([front.material, back.material])
    expect(loaded.coastlines).toBe(true)
    expect(bothExistedWhenLoaded).toBe(true)
    expect(ctx.globeLayerTiersRef.current.coastlines).toEqual({ committed: 'start', inFlight: {}, failed: {}, deferred: {} })
  })

  it('fades a visible layer in from zero, front and back, as today', async () => {
    routes.set(COAST_START, { features: lines(1) })
    const { ctx, fade } = makeCtx()
    await loadVectorLayer('coastlines', ctx)
    const front = ctx.frontLineLayersRef.current.coastlines[0]
    const back = ctx.backLineLayersRef.current.coastlines[0]
    expect(front.visible && back.visible).toBe(true)
    expect(fade.mock.calls.map(c => [c[0], c[1], c[2]])).toEqual([
      ['coastlines', [front.material], 1],
      ['coastlines_back', [back.material], 1],
    ])
  })

  it('reads visibility and satellite mode when it finishes, not when it started', async () => {
    routes.set(BORDERS_START, { features: lines(1) })
    const release = hold(BORDERS_START)
    const { ctx, fade } = makeCtx()
    const done = loadVectorLayer('countryBorders', ctx)
    ctx.vectorLayersRef.current.countryBorders = false
    release()
    await done
    const front = ctx.frontLineLayersRef.current.countryBorders[0]
    expect(front.visible).toBe(false)
    expect((front.material as THREE.ShaderMaterial).uniforms.uOpacity.value).toBe(0)
    expect(fade).not.toHaveBeenCalled()

    routes.set(COAST_START, { features: lines(1) })
    const release2 = hold(COAST_START)
    const second = makeCtx()
    const done2 = loadVectorLayer('coastlines', second.ctx)
    second.ctx.satelliteModeRef.current = true
    release2()
    await done2
    expect(second.ctx.frontLineLayersRef.current.coastlines[0].visible).toBe(true)
    expect(second.ctx.backLineLayersRef.current.coastlines[0].visible).toBe(false)
    expect(second.fade.mock.calls.map(c => c[0])).toEqual(['coastlines'])
  })

  it('marks the layer as loading while it loads and clears it on commit', async () => {
    routes.set(COAST_START, { features: lines(1) })
    const release = hold(COAST_START)
    const { ctx, loading } = makeCtx()
    const done = loadVectorLayer('coastlines', ctx)
    expect(loading.coastlines).toBe(true)
    release()
    await done
    expect(loading.coastlines).toBe(false)
  })

  it('reports a failed critical layer once through onStartError and marks it failed', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { ctx, loaded, loading } = makeCtx()
    await loadVectorLayer('coastlines', ctx)
    expect(ctx.onStartError).toHaveBeenCalledTimes(1)
    const [phase, err] = vi.mocked(ctx.onStartError).mock.calls[0]
    expect(phase).toBe('coastlines')
    expect(String(err)).toContain(`${COAST_START}: HTTP 404`)
    expect(ctx.failedLayersRef.current.coastlines).toBe(true)
    expect(loaded.coastlines).toBeUndefined()
    expect(loading.coastlines).toBe(false)
    expect(ctx.frontLineLayersRef.current.coastlines).toEqual([])
    expect(error).toHaveBeenCalled()
  })

  it('reports an offline start whose start tier is not cached, naming the file', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    routes.set(COAST_START, { features: lines(1) })
    vi.stubGlobal('caches', { open: async () => ({ match: async () => undefined }) })
    OfflineFetch.setOfflineMode(true)
    try {
      const { ctx } = makeCtx()
      await loadVectorLayer('coastlines', ctx)
      expect(fetched).toEqual([])
      expect(ctx.onStartError).toHaveBeenCalledTimes(1)
      expect(vi.mocked(ctx.onStartError).mock.calls[0][1]).toBeInstanceOf(OfflineNotCachedError)
      expect(String(vi.mocked(ctx.onStartError).mock.calls[0][1])).toContain(COAST_START)
    } finally {
      OfflineFetch.setOfflineMode(false)
    }
  })

  it('reports a body the worker cannot parse with the URL', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    routes.set(BORDERS_START, { features: lines(1) })
    const { ctx } = makeCtx({ parseLayer: vi.fn(async () => { throw new Error('Unexpected token <') }) })
    await loadVectorLayer('countryBorders', ctx)
    expect(String(vi.mocked(ctx.onStartError).mock.calls[0][1])).toContain(BORDERS_START)
  })

  it('logs an optional layer failure without reporting a start error', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { ctx } = makeCtx()
    await loadVectorLayer('rivers', ctx)
    expect(ctx.onStartError).not.toHaveBeenCalled()
    expect(ctx.failedLayersRef.current.rivers).toBe(true)
    expect(error).toHaveBeenCalled()
    // A later load that succeeds (another detail level, a new toggle) clears the mark
    routes.set(getLayerUrl('rivers', 'ultra-low'), { features: lines(1) })
    await loadVectorLayer('rivers', ctx)
    expect(ctx.failedLayersRef.current.rivers).toBeUndefined()
  })

  it('drops a load cancelled by the Globe unmount without reporting it', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    routes.set(COAST_START, { features: lines(1) })
    hold(COAST_START)
    const { ctx, abort, loading } = makeCtx()
    const done = loadVectorLayer('coastlines', ctx)
    abort.abort()
    await done
    expect(ctx.onStartError).not.toHaveBeenCalled()
    expect(ctx.failedLayersRef.current.coastlines).toBeUndefined()
    expect(ctx.frontLineLayersRef.current.coastlines).toEqual([])
    expect(loading.coastlines).toBe(true)
    expect(error).not.toHaveBeenCalled()
  })

  it('creates river labels from the worker result, once per name', async () => {
    routes.set(getLayerUrl('rivers', 'ultra-low'), { features: [...lines(2, true), ...lines(1, true)] })
    const { ctx, scene } = makeCtx()
    await loadVectorLayer('rivers', ctx)
    expect(ctx.layerLabelsRef.current.rivers.map(l => l.label.name)).toEqual(['L0', 'L1'])
    expect(ctx.layerLabelsRef.current.rivers[0].label).toMatchObject({ lat: 10.25, lng: 0.25, type: 'river', layerBased: true })
    expect(scene.children).toHaveLength(2)
    expect(ctx.allLabelMeshesRef.current).toHaveLength(2)
  })
})

describe('LOD reloads', () => {
  it('discard a stale load: the newest detail level wins whatever finishes first', async () => {
    const coarse = getLayerUrl('rivers', 'ultra-low')
    const fine = getLayerUrl('rivers', 'low')
    routes.set(coarse, { features: lines(1) })
    routes.set(fine, { features: lines(4) })
    const releaseCoarse = hold(coarse)
    const { ctx } = makeCtx()
    const first = loadVectorLayer('rivers', ctx)
    ctx.detailLevelRef.current = 'low'
    const second = loadVectorLayer('rivers', ctx)
    await second
    releaseCoarse()
    await first
    expect(ctx.frontLineLayersRef.current.rivers).toHaveLength(1)
    expect(ctx.frontLineLayersRef.current.rivers[0].geometry.getAttribute('position').count).toBe(8)
    expect(ctx.shaderMaterialsRef.current).toHaveLength(2)
  })

  it('cross-fade front and back and release the old materials', async () => {
    const coarse = getLayerUrl('lakes', 'ultra-low')
    const fine = getLayerUrl('lakes', 'low')
    routes.set(coarse, { features: lines(1) })
    routes.set(fine, { features: lines(2) })
    const { ctx, globe, fade } = makeCtx()
    await loadVectorLayer('lakes', ctx)
    const [oldFront] = ctx.frontLineLayersRef.current.lakes
    const [oldBack] = ctx.backLineLayersRef.current.lakes
    const oldFrontDispose = vi.spyOn(oldFront.geometry, 'dispose')
    const oldBackDispose = vi.spyOn(oldBack.geometry, 'dispose')
    fade.mockClear()

    ctx.detailLevelRef.current = 'low'
    await loadVectorLayer('lakes', ctx)

    const [front] = ctx.frontLineLayersRef.current.lakes
    const [back] = ctx.backLineLayersRef.current.lakes
    expect(fade.mock.calls.map(c => [c[0], c[2], c[3]?.duration])).toEqual([
      ['lakes_lod_old_2', 0, 100], ['lakes', 1, 100],
      ['lakes_back_lod_old_2', 0, 100], ['lakes_back', 1, 100],
    ])
    expect(globe.children).toEqual([front, back])
    expect(ctx.shaderMaterialsRef.current).toEqual([front.material, back.material])
    expect(oldFrontDispose).toHaveBeenCalledTimes(1)
    expect(oldBackDispose).toHaveBeenCalledTimes(1)
  })
})

describe('pickLayersToLoad', () => {
  it('never picks a layer that failed, is loaded, is loading or is off', () => {
    const visible = { coastlines: true, countryBorders: true, rivers: true, lakes: true, coralReefs: true, glaciers: false, plateBoundaries: true }
    expect(pickLayersToLoad(visible, { rivers: true }, { lakes: true }, { coastlines: true, coralReefs: true }))
      .toEqual(['countryBorders', 'plateBoundaries'])
  })
})

// ---------------------------------------------------------------------------
// Background tiers
// ---------------------------------------------------------------------------

async function startTier(key: GlobeLayerKey, ctx: VectorRendererContext) {
  routes.set(key === 'coastlines' ? COAST_START : BORDERS_START, { features: lines(1) })
  await loadVectorLayer(key, ctx)
}

describe('upgradeLayerTier', () => {
  it('swaps the geometry in place: same lines, same materials, no fade, no state', async () => {
    const { ctx, globe, fade } = makeCtx()
    await startTier('coastlines', ctx)
    const [front] = ctx.frontLineLayersRef.current.coastlines
    const [back] = ctx.backLineLayersRef.current.coastlines
    const frontMat = front.material as THREE.ShaderMaterial
    const opacity = frontMat.uniforms.uOpacity.value
    const oldFront = front.geometry
    const oldBack = back.geometry
    const disposeFront = vi.spyOn(oldFront, 'dispose')
    const disposeBack = vi.spyOn(oldBack, 'dispose')
    fade.mockClear()
    vi.mocked(ctx.setIsLoadingLayers).mockClear()
    vi.mocked(ctx.setLayersLoaded).mockClear()
    routes.set(COAST_DETAIL, { features: lines(5) })

    await upgradeLayerTier('coastlines', 'detail', ctx, new AbortController().signal)

    expect(ctx.frontLineLayersRef.current.coastlines).toEqual([front])
    expect(ctx.backLineLayersRef.current.coastlines).toEqual([back])
    expect(front.material).toBe(frontMat)
    expect(frontMat.uniforms.uOpacity.value).toBe(opacity)
    expect(front.visible && back.visible).toBe(true)
    expect(front.geometry).not.toBe(oldFront)
    expect(front.geometry.getAttribute('position').count).toBe(10)
    expect(vertexRadius(back)).toBeCloseTo(1.001, 6)
    expect(globe.children).toEqual([front, back])
    expect(disposeFront).toHaveBeenCalledTimes(1)
    expect(disposeBack).toHaveBeenCalledTimes(1)
    expect(fade).not.toHaveBeenCalled()
    expect(ctx.setIsLoadingLayers).not.toHaveBeenCalled()
    expect(ctx.setLayersLoaded).not.toHaveBeenCalled()
    expect(ctx.globeLayerTiersRef.current.coastlines).toEqual({ committed: 'detail', inFlight: {}, failed: {}, deferred: {} })
  })

  it('never downgrades: a detail tier that arrives after hires is discarded', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    routes.set(COAST_DETAIL, { features: lines(5) })
    routes.set(COAST_HIRES, { features: lines(9) })
    const releaseDetail = hold(COAST_DETAIL)
    const signal = new AbortController().signal
    const detail = upgradeLayerTier('coastlines', 'detail', ctx, signal)
    await upgradeLayerTier('coastlines', 'hires', ctx, signal)
    releaseDetail()
    await detail
    expect(ctx.frontLineLayersRef.current.coastlines[0].geometry.getAttribute('position').count).toBe(18)
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('hires')
    await upgradeLayerTier('coastlines', 'detail', ctx, signal)
    expect(fetched.filter(u => u === COAST_DETAIL)).toHaveLength(1)
  })

  it('does not fetch a tier twice while it is on its way: a second request joins the load', async () => {
    const { ctx } = makeCtx()
    await startTier('countryBorders', ctx)
    routes.set(BORDERS_DETAIL, { features: lines(2) })
    const release = hold(BORDERS_DETAIL)
    const signal = new AbortController().signal
    const first = upgradeLayerTier('countryBorders', 'detail', ctx, signal)
    const second = upgradeLayerTier('countryBorders', 'detail', ctx, signal)
    release()
    await Promise.all([first, second])
    expect(fetched.filter(u => u === BORDERS_DETAIL)).toHaveLength(1)
    expect(ctx.globeLayerTiersRef.current.countryBorders.committed).toBe('detail')
  })

  it('never fetches a failed tier again, and never resolves without it', async () => {
    const { ctx } = makeCtx()
    await startTier('countryBorders', ctx)
    const signal = new AbortController().signal
    await expect(upgradeLayerTier('countryBorders', 'detail', ctx, signal)).rejects.toThrow(`${BORDERS_DETAIL}: HTTP 404`)
    await expect(upgradeLayerTier('countryBorders', 'detail', ctx, signal)).rejects.toThrow(`${BORDERS_DETAIL}: HTTP 404`)
    expect(fetched.filter(u => u === BORDERS_DETAIL)).toHaveLength(1)
    expect(ctx.globeLayerTiersRef.current.countryBorders.committed).toBe('start')
    expect(ctx.onStartError).not.toHaveBeenCalled()
  })

  it('loads the detail tier while hires is on its way, and hires still lands on top', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    routes.set(COAST_DETAIL, { features: lines(5) })
    routes.set(COAST_HIRES, { features: lines(9) })
    const releaseHires = hold(COAST_HIRES)
    const signal = new AbortController().signal
    const hires = upgradeLayerTier('coastlines', 'hires', ctx, signal)
    await upgradeLayerTier('coastlines', 'detail', ctx, signal)
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('detail')
    expect(ctx.frontLineLayersRef.current.coastlines[0].geometry.getAttribute('position').count).toBe(10)
    releaseHires()
    await hires
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('hires')
    expect(ctx.frontLineLayersRef.current.coastlines[0].geometry.getAttribute('position').count).toBe(18)
  })

  it('loads the detail tier after a failed hires tier', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    const signal = new AbortController().signal
    await expect(upgradeLayerTier('coastlines', 'hires', ctx, signal)).rejects.toThrow(`${COAST_HIRES}: HTTP 404`)
    routes.set(COAST_DETAIL, { features: lines(5) })
    await upgradeLayerTier('coastlines', 'detail', ctx, signal)
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('detail')
  })

  it('lets a cancelled tier be asked for again', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    routes.set(COAST_DETAIL, { features: lines(5) })
    hold(COAST_DETAIL)
    const task = new AbortController()
    const cancelled = upgradeLayerTier('coastlines', 'detail', ctx, task.signal)
    task.abort()
    await expect(cancelled).rejects.toMatchObject({ name: 'AbortError' })
    held.clear()
    await upgradeLayerTier('coastlines', 'detail', ctx, new AbortController().signal)
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('detail')
  })

  it('fails loudly when the start tier is not on the globe', async () => {
    const { ctx } = makeCtx()
    await expect(upgradeLayerTier('coastlines', 'detail', ctx, new AbortController().signal)).rejects.toThrow(/coastlines/)
  })

  it('rejects with an AbortError when the task is aborted and leaves the start tier', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    routes.set(COAST_DETAIL, { features: lines(5) })
    hold(COAST_DETAIL)
    const task = new AbortController()
    const done = upgradeLayerTier('coastlines', 'detail', ctx, task.signal)
    task.abort()
    await expect(done).rejects.toMatchObject({ name: 'AbortError' })
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('start')
  })
})

describe('upgradeGlobeLayers', () => {
  it('commits the detail tier even when a hi-res coastline failed first', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    await startTier('countryBorders', ctx)
    await expect(upgradeLayerTier('coastlines', 'hires', ctx, new AbortController().signal)).rejects.toThrow(/HTTP 404/)
    routes.set(COAST_DETAIL, { features: lines(2) })
    routes.set(BORDERS_DETAIL, { features: lines(2) })
    await upgradeGlobeLayers(ctx, new AbortController().signal)
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('detail')
    expect(ctx.globeLayerTiersRef.current.countryBorders.committed).toBe('detail')
  })

  it('brings coastlines and borders to the detail tier', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    await startTier('countryBorders', ctx)
    routes.set(COAST_DETAIL, { features: lines(2) })
    routes.set(BORDERS_DETAIL, { features: lines(2) })
    await upgradeGlobeLayers(ctx, new AbortController().signal)
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('detail')
    expect(ctx.globeLayerTiersRef.current.countryBorders.committed).toBe('detail')
    expect(fetched.slice(2)).toEqual([COAST_DETAIL, BORDERS_DETAIL])
  })

  it('loads the borders even when the coastline fails, then rejects once with the coastline failure', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    await startTier('countryBorders', ctx)
    // No route for the coastline detail tier: its fetch fails (HTTP 404)
    routes.set(BORDERS_DETAIL, { features: lines(2) })
    await expect(upgradeGlobeLayers(ctx, new AbortController().signal)).rejects.toThrow(/HTTP 404/)
    expect(fetched.slice(2)).toEqual([COAST_DETAIL, BORDERS_DETAIL])
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('start')
    expect(ctx.globeLayerTiersRef.current.countryBorders.committed).toBe('detail')
  })

  it('rejects with the first failure when every layer fails', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    await startTier('countryBorders', ctx)
    routes.set(COAST_DETAIL, { status: 503 })
    await expect(upgradeGlobeLayers(ctx, new AbortController().signal)).rejects.toThrow(/HTTP 503/)
    expect(fetched.slice(2)).toEqual([COAST_DETAIL, BORDERS_DETAIL])
  })

  it('stops at an abort: no layer after the cancelled one is fetched', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    await startTier('countryBorders', ctx)
    routes.set(COAST_DETAIL, { features: lines(2) })
    routes.set(BORDERS_DETAIL, { features: lines(2) })
    hold(COAST_DETAIL)
    const task = new AbortController()
    const done = upgradeGlobeLayers(ctx, task.signal)
    task.abort()
    await expect(done).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetched.slice(2)).toEqual([COAST_DETAIL])
    expect(ctx.globeLayerTiersRef.current.countryBorders.committed).toBe('start')
  })

  it('defers a detail tier app offline mode cannot fetch, and loads it once offline mode is off', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    await startTier('countryBorders', ctx)
    routes.set(COAST_DETAIL, { features: lines(2) })
    routes.set(BORDERS_DETAIL, { features: lines(2) })
    // The Offline-Mode button during the intro, or one browser 'offline' event; nothing cached
    vi.stubGlobal('caches', { open: async () => ({ match: async () => undefined }) })
    OfflineFetch.setOfflineMode(true)
    try {
      // Not now is not failed: no rejection (no false globe_error{bg:layers}), no barred tier
      await expect(upgradeGlobeLayers(ctx, new AbortController().signal)).resolves.toBeUndefined()
      expect(fetched.slice(2)).toEqual([])
      expect(ctx.globeLayerTiersRef.current.coastlines.failed).toEqual({})
      expect(ctx.globeLayerTiersRef.current.countryBorders.failed).toEqual({})
      expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('start')
      expect(resumeDeferredGlobeLayers(ctx)).toBeNull() // still offline
    } finally {
      OfflineFetch.setOfflineMode(false)
    }
    await resumeDeferredGlobeLayers(ctx)
    expect(fetched.slice(2)).toEqual([COAST_DETAIL, BORDERS_DETAIL])
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('detail')
    expect(ctx.globeLayerTiersRef.current.countryBorders.committed).toBe('detail')
    expect(resumeDeferredGlobeLayers(ctx)).toBeNull() // nothing deferred any more
  })

  it('ends the deferral when the resumed load fails: the other deferred layer loads in the same resume, one rejection, never the failed one again', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    await startTier('countryBorders', ctx)
    // No route for the coastline detail tier: the resumed fetch fails (HTTP 404)
    routes.set(BORDERS_DETAIL, { features: lines(2) })
    vi.stubGlobal('caches', { open: async () => ({ match: async () => undefined }) })
    OfflineFetch.setOfflineMode(true)
    try {
      await upgradeGlobeLayers(ctx, new AbortController().signal)
    } finally {
      OfflineFetch.setOfflineMode(false)
    }
    // First switch off: the coastline fails once, which Globe reports as bg:layers; the
    // borders still reach their detail tier in that same resume
    await expect(resumeDeferredGlobeLayers(ctx)).rejects.toThrow(/HTTP 404/)
    expect(ctx.globeLayerTiersRef.current.coastlines.deferred).toEqual({})
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('start')
    expect(ctx.globeLayerTiersRef.current.countryBorders.committed).toBe('detail')
    expect(ctx.globeLayerTiersRef.current.countryBorders.deferred).toEqual({})
    expect(fetched.slice(2)).toEqual([COAST_DETAIL, BORDERS_DETAIL])
    // Next switch off: nothing is deferred, so no second load and no second report
    expect(resumeDeferredGlobeLayers(ctx)).toBeNull()
    expect(fetched.slice(2)).toEqual([COAST_DETAIL, BORDERS_DETAIL])
  })

  it('offline, loads a detail tier a Coastlines download holds', async () => {
    const { ctx } = makeCtx()
    await startTier('coastlines', ctx)
    await startTier('countryBorders', ctx)
    const body = JSON.stringify({ type: 'FeatureCollection', features: lines(2) })
    vi.stubGlobal('caches', {
      open: async () => ({ match: async (url: string) => (url === COAST_DETAIL ? new Response(body) : undefined) }),
    })
    OfflineFetch.setOfflineMode(true)
    try {
      await upgradeGlobeLayers(ctx, new AbortController().signal)
    } finally {
      OfflineFetch.setOfflineMode(false)
    }
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('detail')
    expect(ctx.globeLayerTiersRef.current.countryBorders.committed).toBe('start')
    expect(fetched.slice(2)).toEqual([])
  })

  it('Globe resumes the deferred tiers when app offline mode is switched off', async () => {
    const { readFileSync } = await import('node:fs')
    const globe = readFileSync(new URL('../../../Globe.tsx', import.meta.url), 'utf-8')
    expect(globe).toMatch(/OfflineFetch\.onOfflineModeChange\(offline => \{\s*if \(offline\) return\s*resumeDeferredGlobeLayers\(buildVectorRendererContext\(\)\)/)
  })
})

describe('ensureHiresCoastline', () => {
  function gateFor(camera: THREE.Camera, mapbox: { state: string }) {
    return { getMapboxState: () => mapbox.state, getCameraDistance: () => camera.position.length(), switchDistance: 1.304 }
  }

  it('loads coast_hires once, only when Mapbox failed and the camera is closer than the switch', async () => {
    const { ctx, camera } = makeCtx()
    await startTier('coastlines', ctx)
    routes.set(COAST_HIRES, { features: lines(3) })
    const mapbox = { state: 'ready' }
    const gate = gateFor(camera, mapbox)
    const build = () => ctx

    camera.position.set(0, 0, 1.2)
    expect(ensureHiresCoastline(gate, build)).toBeNull()
    mapbox.state = 'failed'
    camera.position.set(0, 0, 1.5)
    expect(ensureHiresCoastline(gate, build)).toBeNull()
    camera.position.set(0, 0, 1.2)
    const first = ensureHiresCoastline(gate, build)
    expect(ensureHiresCoastline(gate, build)).toBeNull()
    await first
    expect(ensureHiresCoastline(gate, build)).toBeNull()
    expect(fetched.filter(u => u === COAST_HIRES)).toHaveLength(1)
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('hires')
  })

  it('builds no context while the gate is closed', () => {
    const { ctx, camera } = makeCtx()
    const build = vi.fn(() => ctx)
    const mapbox = { state: 'ready' }
    camera.position.set(0, 0, 1.2)
    expect(ensureHiresCoastline(gateFor(camera, mapbox), build)).toBeNull()
    mapbox.state = 'failed'
    camera.position.set(0, 0, 2.44)
    expect(ensureHiresCoastline(gateFor(camera, mapbox), build)).toBeNull()
    expect(build).not.toHaveBeenCalled()
  })

  it('does not ask again for a hi-res coastline that failed', async () => {
    const { ctx, camera } = makeCtx()
    await startTier('coastlines', ctx)
    const gate = gateFor(camera, { state: 'failed' })
    camera.position.set(0, 0, 1.2)
    await expect(ensureHiresCoastline(gate, () => ctx)).rejects.toThrow(/HTTP 404/)
    expect(ensureHiresCoastline(gate, () => ctx)).toBeNull()
    expect(fetched.filter(u => u === COAST_HIRES)).toHaveLength(1)
  })

  it('offline, leaves a hi-res coastline no cache holds for later: not barred, not reported, loaded once offline mode is off', async () => {
    const { ctx, camera } = makeCtx()
    await startTier('coastlines', ctx)
    routes.set(COAST_HIRES, { features: lines(3) })
    // An offline start: the Mapbox style fetch failed, and a sources-only download holds no coast_hires
    vi.stubGlobal('caches', { open: async () => ({ match: async () => undefined }) })
    const gate = gateFor(camera, { state: 'failed' })
    camera.position.set(0, 0, 1.2)
    OfflineFetch.setOfflineMode(true)
    try {
      // Not now is not failed: no rejection, so Globe sends no globe_error{bg:hires}
      await expect(ensureHiresCoastline(gate, () => ctx)).resolves.toBeUndefined()
      expect(ctx.globeLayerTiersRef.current.coastlines.failed).toEqual({})
      expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('start')
      // Camera changes while offline mode is on do not ask the cache again and again
      expect(ensureHiresCoastline(gate, () => ctx)).toBeNull()
    } finally {
      OfflineFetch.setOfflineMode(false)
    }
    expect(fetched.filter(u => u === COAST_HIRES)).toHaveLength(0)
    // The next close-zoom camera change after offline mode is off loads it
    await ensureHiresCoastline(gate, () => ctx)
    expect(ctx.globeLayerTiersRef.current.coastlines.committed).toBe('hires')
    expect(fetched.filter(u => u === COAST_HIRES)).toHaveLength(1)
    expect(ensureHiresCoastline(gate, () => ctx)).toBeNull()
  })
})

describe('preloadRiversLakes', () => {
  it('parses the files a toggle at the current zoom needs, and the toggle reuses them', async () => {
    const rivers = getLayerUrl('rivers', 'low')
    const lakes = getLayerUrl('lakes', 'low')
    routes.set(rivers, { features: lines(2) })
    routes.set(lakes, { features: lines(3) })
    const { ctx, globe } = makeCtx()
    ctx.detailLevelRef.current = 'low'

    await preloadRiversLakes(ctx, new AbortController().signal)
    expect(fetched).toEqual([rivers, lakes])
    expect(globe.children).toEqual([])

    await loadVectorLayer('rivers', ctx)
    await loadVectorLayer('lakes', ctx)
    expect(fetched).toEqual([rivers, lakes])
    expect(ctx.parseLayer).toHaveBeenCalledTimes(2)
    expect(ctx.frontLineLayersRef.current.lakes[0].geometry.getAttribute('position').count).toBe(6)
  })

  it('rejects when a file fails, and a later toggle fetches again', async () => {
    const { ctx } = makeCtx()
    await expect(preloadRiversLakes(ctx, new AbortController().signal)).rejects.toThrow(/HTTP 404/)
    routes.set(getLayerUrl('rivers', 'ultra-low'), { features: lines(1) })
    await loadVectorLayer('rivers', ctx)
    expect(ctx.frontLineLayersRef.current.rivers).toHaveLength(1)
  })
})

describe('every URL the loader fetches', () => {
  it('is one of getLayerFiles, so the offline download covers it', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { ctx } = makeCtx()
    for (const detail of ['ultra-low', 'low', 'medium', 'high'] as const) {
      ctx.detailLevelRef.current = detail
      for (const key of ['rivers', 'lakes', 'coralReefs', 'glaciers', 'plateBoundaries'] as const) await loadVectorLayer(key, ctx)
    }
    await loadVectorLayer('coastlines', ctx)
    await loadVectorLayer('countryBorders', ctx)
    for (const url of fetched) {
      const owner = (Object.keys(ctx.vectorLayersRef.current) as VectorLayerKey[]).find(k => getLayerFiles(k).includes(url))
      expect(owner, url).toBeDefined()
    }
  })
})

// ---------------------------------------------------------------------------
// The worker client
// ---------------------------------------------------------------------------

class FakeWorker {
  onmessage: ((e: MessageEvent<LayerWorkerResponse>) => void) | null = null
  onerror: ((e: ErrorEvent) => void) | null = null
  posted: Array<{ msg: LayerWorkerRequest; transfer: Transferable[] }> = []
  terminated = false
  postMessage(msg: LayerWorkerRequest, options: { transfer: Transferable[] }) {
    this.posted.push({ msg, transfer: options.transfer })
  }
  terminate() { this.terminated = true }
  answer(i: number) {
    const { response } = processLayerRequest(this.posted[i].msg)
    this.onmessage?.({ data: response } as MessageEvent<LayerWorkerResponse>)
  }
}

describe('createLayerParser', () => {
  function bytes(json: string): ArrayBuffer {
    return new TextEncoder().encode(json).buffer as ArrayBuffer
  }

  it('creates its worker on the first parse and transfers the bytes', async () => {
    const worker = new FakeWorker()
    const create = vi.fn(() => worker as unknown as Worker)
    const parser = createLayerParser(create)
    expect(create).not.toHaveBeenCalled()
    const buffer = bytes('{"type":"FeatureCollection","features":[]}')
    const result = parser.parse(buffer, [1.002, 1.001], false)
    expect(create).toHaveBeenCalledTimes(1)
    expect(worker.posted[0].transfer).toEqual([buffer])
    expect(worker.posted[0].msg).toMatchObject({ radii: [1.002, 1.001], withLabels: false })
    worker.answer(0)
    await expect(result).resolves.toEqual({ positions: [new Float32Array(0), new Float32Array(0)], labels: undefined })
    parser.parse(bytes('{"type":"FeatureCollection","features":[]}'), [1], false)
    expect(create).toHaveBeenCalledTimes(1)
  })

  it('rejects with the worker error message', async () => {
    const worker = new FakeWorker()
    const parser = createLayerParser(() => worker as unknown as Worker)
    const result = parser.parse(bytes('not json'), [1], false)
    worker.answer(0)
    await expect(result).rejects.toThrow(/JSON/)
  })

  it('fails every pending and later parse when the worker itself breaks', async () => {
    const worker = new FakeWorker()
    const parser = createLayerParser(() => worker as unknown as Worker)
    const pending = parser.parse(bytes('{}'), [1], false)
    worker.onerror?.({ message: 'chunk failed to load' } as ErrorEvent)
    await expect(pending).rejects.toThrow('chunk failed to load')
    await expect(parser.parse(bytes('{}'), [1], false)).rejects.toThrow('chunk failed to load')
    expect(worker.terminated).toBe(true)
  })

  it('terminates on dispose and cancels what is pending', async () => {
    const worker = new FakeWorker()
    const parser = createLayerParser(() => worker as unknown as Worker)
    const pending = parser.parse(bytes('{}'), [1], false)
    parser.dispose()
    expect(worker.terminated).toBe(true)
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    await expect(parser.parse(bytes('{}'), [1], false)).rejects.toMatchObject({ name: 'AbortError' })
  })
})
