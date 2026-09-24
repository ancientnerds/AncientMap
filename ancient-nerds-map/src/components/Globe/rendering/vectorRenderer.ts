/**
 * Vector layer rendering: coastlines, borders, rivers, lakes, glaciers, coral reefs and
 * tectonic plate boundaries, each drawn twice (front of the globe, and dimmed through it).
 *
 * One fetch per layer file, one parse in the layer worker, and front and back built from that
 * one result in the same synchronous step. Coastlines and borders start on their start tier;
 * the background queue swaps in the detail tier in place (same line, same material, no fade).
 * Nothing here depends on requestAnimationFrame, so a load in a hidden tab completes.
 */

import * as THREE from 'three'
import {
  GLOBE_LAYER_KEYS,
  LAYER_CONFIG,
  getGlobeLayerUrl,
  getLayerUrl,
  isGlobeLayerKey,
  tierRank,
  type GlobeLayerKey,
  type GlobeLayerTierState,
  type UpgradeTier,
  type VectorLayerKey,
  type VectorLayerVisibility,
} from '../../../config/vectorLayers'
import type { DetailLevel } from '../../../config/globeConstants'
import { LABEL_BASE_SCALE } from '../../../config/globeConstants'
import { OfflineFetch, OfflineNotCachedError, offlineFetch } from '../../../services/OfflineFetch'
import { createFrontLineMaterial as createFrontMaterial, createBackLineMaterial as createBackMaterial } from '../../../shaders/globe'
import { createLabelTexture, createGlobeTangentLabel, type GlobeLabelMesh } from '../../../utils/LabelRenderer'
import type { FadeManager } from '../../../utils/FadeManager'
import { latLngTo3DArray, type LayerWorkerRequest, type LayerWorkerResponse, type LineLabel } from './segmentBuilder'

export interface GeoLabel {
  name: string
  lat: number
  lng: number
  type: 'continent' | 'country' | 'capital' | 'ocean' | 'sea' | 'region' | 'mountain' | 'desert' | 'lake' | 'river' | 'metropol' | 'city' | 'plate' | 'glacier' | 'coralReef'
  rank: number
  hidden?: boolean
  layerBased?: boolean
  country?: string
  national?: boolean
  detailLevel?: number
}

export interface GlobeLabel {
  label: GeoLabel
  mesh: GlobeLabelMesh
  position: THREE.Vector3
}

/** What the worker hands back: one Float32Array per requested radius, river/lake names if asked. */
export interface ParsedLayer {
  positions: Float32Array[]
  labels?: LineLabel[]
}

export type ParseLayer = (buffer: ArrayBuffer, radii: readonly number[], withLabels: boolean) => Promise<ParsedLayer>

/** Shared context required by the vector renderer functions. Everything is read when used. */
export interface VectorRendererContext {
  sceneRef: React.MutableRefObject<{
    renderer: THREE.WebGLRenderer
    scene: THREE.Scene
    camera: THREE.PerspectiveCamera
    controls: any
    points: THREE.Points | null
    backPoints: THREE.Points | null
    shadowPoints: THREE.Points | null
    globe: THREE.Mesh
  } | null>

  shaderMaterialsRef: React.MutableRefObject<THREE.ShaderMaterial[]>
  frontLineLayersRef: React.MutableRefObject<Record<VectorLayerKey, THREE.Line[]>>
  backLineLayersRef: React.MutableRefObject<Record<VectorLayerKey, THREE.Line[]>>
  fadeManagerRef: React.MutableRefObject<FadeManager>
  detailLevelRef: React.MutableRefObject<DetailLevel>
  layerLabelsRef: React.MutableRefObject<Record<string, GlobeLabel[]>>
  allLabelMeshesRef: React.MutableRefObject<GlobeLabelMesh[]>
  updateGeoLabelsRef: React.MutableRefObject<(() => void) | null>

  /** Visibility and satellite mode, read when a load finishes: a toggle may land while it runs. */
  vectorLayersRef: React.MutableRefObject<Record<VectorLayerKey, boolean>>
  satelliteModeRef: React.MutableRefObject<boolean>
  /** Newest load per layer: an older load that finishes later is discarded, never the newer one. */
  layerLoadIdsRef: React.MutableRefObject<Record<string, number>>
  globeLayerTiersRef: React.MutableRefObject<Record<GlobeLayerKey, GlobeLayerTierState>>
  /** Layers whose load failed; the load effect does not pick them again (no retry loop). */
  failedLayersRef: React.MutableRefObject<Partial<Record<VectorLayerKey, boolean>>>

  /** React state setters */
  setIsLoadingLayers: React.Dispatch<React.SetStateAction<Record<string, boolean>>>
  setLayersLoaded: React.Dispatch<React.SetStateAction<Record<string, boolean>>>

  /** Parses a layer file off the main thread (createLayerParser). */
  parseLayer: ParseLayer
  /** Aborted when the Globe unmounts: loads still in flight are dropped, not reported. */
  signal: AbortSignal
  /** Contract C0: a critical layer that cannot load is reported here, once. */
  onStartError: (phase: string, err: unknown) => void
}

/** When the hi-res coastline may load (plan U6.5): Mapbox cannot take over below the switch. */
export interface HiresCoastlineGate {
  getMapboxState: () => string
  getCameraDistance: () => number
  switchDistance: number
}

// ---------------------------------------------------------------------------
// Worker client
// ---------------------------------------------------------------------------

export interface LayerParser {
  parse: ParseLayer
  dispose(): void
}

function abortError(what: string): DOMException {
  return new DOMException(what, 'AbortError')
}

export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

/**
 * One layer worker per Globe, created on the first parse and terminated by dispose(). A worker
 * that fails (its chunk does not load, it crashes) fails every pending and later parse with
 * its message; it is not recreated.
 */
export function createLayerParser(
  createWorker: () => Worker = () => new Worker(new URL('./layerWorker.ts', import.meta.url), { type: 'module' }),
): LayerParser {
  let worker: Worker | null = null
  let broken: Error | null = null
  let nextId = 0
  const pending = new Map<number, { resolve: (parsed: ParsedLayer) => void; reject: (err: unknown) => void }>()

  const rejectAll = (err: unknown) => {
    pending.forEach(p => p.reject(err))
    pending.clear()
  }

  const start = (): Worker => {
    if (worker) return worker
    const w = createWorker()
    w.onmessage = (event: MessageEvent<LayerWorkerResponse>) => {
      const data = event.data
      const entry = pending.get(data.id)
      if (!entry) return
      pending.delete(data.id)
      if ('error' in data) entry.reject(new Error(data.error))
      else entry.resolve({ positions: data.positions, labels: data.labels })
    }
    w.onerror = (event: ErrorEvent) => {
      broken = new Error(`Layer worker failed: ${event.message}`)
      w.terminate()
      rejectAll(broken)
    }
    worker = w
    return w
  }

  return {
    parse(buffer, radii, withLabels) {
      if (broken) return Promise.reject(broken)
      const id = ++nextId
      return new Promise<ParsedLayer>((resolve, reject) => {
        pending.set(id, { resolve, reject })
        const request: LayerWorkerRequest = { id, buffer, radii, withLabels }
        start().postMessage(request, { transfer: [buffer] })
      })
    },
    dispose() {
      broken = abortError('Layer parser disposed')
      worker?.terminate()
      worker = null
      rejectAll(broken)
    },
  }
}

// ---------------------------------------------------------------------------
// Fetch and parse
// ---------------------------------------------------------------------------

function throwIfAborted(signal: AbortSignal): void {
  if (signal.aborted) throw abortError('Vector layer load aborted')
}

/** A signal that aborts with either input; release() detaches it from both. */
function linkSignals(a: AbortSignal, b: AbortSignal): { signal: AbortSignal; release: () => void } {
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (a.aborted || b.aborted) controller.abort()
  a.addEventListener('abort', abort)
  b.addEventListener('abort', abort)
  return {
    signal: controller.signal,
    release: () => {
      a.removeEventListener('abort', abort)
      b.removeEventListener('abort', abort)
    },
  }
}

export async function fetchLayerBuffer(url: string, signal: AbortSignal): Promise<ArrayBuffer> {
  const response = await offlineFetch(url, { signal })
  if (!response.ok) throw new Error(`Vector layer ${url}: HTTP ${response.status}`)
  return response.arrayBuffer()
}

/** Front radius (LAYER_CONFIG) and back radius just inside it. */
function layerRadii(layerKey: VectorLayerKey): [number, number] {
  const radius = LAYER_CONFIG[layerKey].radius
  return [radius, radius - 0.001]
}

async function fetchAndParse(url: string, layerKey: VectorLayerKey, ctx: VectorRendererContext, signal: AbortSignal): Promise<ParsedLayer> {
  const buffer = await fetchLayerBuffer(url, signal)
  throwIfAborted(signal)
  const withLabels = layerKey === 'rivers' || layerKey === 'lakes'
  try {
    return await ctx.parseLayer(buffer, layerRadii(layerKey), withLabels)
  } catch (err) {
    if (isAbortError(err)) throw err
    throw new Error(`Vector layer ${url}: ${err instanceof Error ? err.message : String(err)}`)
  }
}

/**
 * Parsed rivers/lakes files from the background preload (queue task `rivers_lakes`), keyed by
 * URL. Module level, so a Globe remount (the phone-gate resize) keeps them.
 */
const parsedLayerCache = new Map<string, Promise<ParsedLayer>>()

export function _resetParsedLayerCacheForTests(): void {
  parsedLayerCache.clear()
}

// ---------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------

function segmentGeometry(positions: Float32Array, radius: number): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry()
  // The CPU copy stays: a restored WebGL context re-uploads from it.
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  // Set bounding sphere manually (positions all sit near the unit sphere)
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), radius + 0.01)
  return geometry
}

/**
 * Replace a line's geometry in place: the same Line (pending fade-out callbacks and the
 * satellite toggle hold it) and the same material, so no fade, no flash and no state change.
 */
function swapGeometry(line: THREE.Line, positions: Float32Array, radius: number): void {
  const old = line.geometry
  line.geometry = segmentGeometry(positions, radius)
  old.dispose()
}

/** Fade retired LOD lines out, then remove them and release their materials. */
function retireLines(key: string, lines: THREE.Line[], ctx: VectorRendererContext, globe: THREE.Mesh): void {
  if (lines.length === 0) return
  const materials = lines.map(line => line.material as THREE.ShaderMaterial)
  ctx.fadeManagerRef.current.fadeTo(key, materials, 0, {
    duration: 100,
    onComplete: () => {
      materials.forEach(mat => {
        const idx = ctx.shaderMaterialsRef.current.indexOf(mat)
        if (idx !== -1) ctx.shaderMaterialsRef.current.splice(idx, 1)
      })
      lines.forEach(line => {
        globe.remove(line)
        line.geometry.dispose()
        ;(line.material as THREE.Material).dispose()
      })
    },
  })
}

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

/** River and lake names from the worker, one label per name. */
function addLineLabels(layerKey: 'rivers' | 'lakes', labels: LineLabel[], ctx: VectorRendererContext, scene: THREE.Scene): void {
  const labelType = layerKey === 'lakes' ? 'lake' : 'river'
  const existingNames = new Set(ctx.layerLabelsRef.current[layerKey].map(item => item.label.name))
  for (const candidate of labels) {
    if (existingNames.has(candidate.name)) continue
    const { texture, width, height } = createLabelTexture(candidate.name, labelType)
    const position = new THREE.Vector3(...latLngTo3DArray(candidate.lat, candidate.lng, 1.0045))
    const baseScale = LABEL_BASE_SCALE[labelType] ?? 0.04
    // Lake/river labels render BELOW continent/country labels
    const mesh = createGlobeTangentLabel(texture, position, baseScale, width / height, 950)
    mesh.visible = false
    scene.add(mesh)
    ctx.allLabelMeshesRef.current.push(mesh)
    const label: GeoLabel = { name: candidate.name, lat: candidate.lat, lng: candidate.lng, type: labelType, rank: candidate.rank, layerBased: true }
    ctx.layerLabelsRef.current[layerKey].push({ label, mesh, position })
    existingNames.add(candidate.name)
  }
  // Trigger visibility update
  setTimeout(() => ctx.updateGeoLabelsRef.current?.(), 0)
}

/** Point-label files (pre-computed centroids) of the plate, glacier and coral reef layers. */
const POINT_LABELS = {
  plateBoundaries: { type: 'plate', baseScale: 0.035, renderOrder: 940 },  // Slightly smaller than ocean labels
  glaciers: { type: 'glacier', baseScale: 0.032, renderOrder: 935 },
  coralReefs: { type: 'coralReef', baseScale: 0.028, renderOrder: 930 },
} as const

type PointLabelLayer = keyof typeof POINT_LABELS

async function loadPointLabels(layerKey: PointLabelLayer, ctx: VectorRendererContext): Promise<void> {
  const url = LAYER_CONFIG[layerKey].labelsFile
  const { type, baseScale, renderOrder } = POINT_LABELS[layerKey]
  const response = await offlineFetch(url, { signal: ctx.signal })
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
  const data = await response.json() as { features: Array<{ properties?: { name?: string }; geometry: { coordinates: [number, number] } }> }
  const sceneData = ctx.sceneRef.current
  if (ctx.signal.aborted || !sceneData) return
  for (const feature of data.features) {
    const name = feature.properties?.name
    if (!name) continue
    const [lng, lat] = feature.geometry.coordinates
    const { texture, width, height } = createLabelTexture(name, type)
    const position = new THREE.Vector3(...latLngTo3DArray(lat, lng, 1.0045))
    const mesh = createGlobeTangentLabel(texture, position, baseScale, width / height, renderOrder)
    mesh.visible = false
    sceneData.scene.add(mesh)
    ctx.allLabelMeshesRef.current.push(mesh)
    // All plates, glaciers and reefs have the same priority
    ctx.layerLabelsRef.current[layerKey].push({ label: { name, lat, lng, type, rank: 1, layerBased: true }, mesh, position })
  }
  // Trigger visibility update
  setTimeout(() => ctx.updateGeoLabelsRef.current?.(), 0)
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

/** The enabled layers the load effect should start: not loaded, not loading, not failed. */
export function pickLayersToLoad(
  visibility: VectorLayerVisibility,
  loaded: Record<string, boolean>,
  loading: Record<string, boolean>,
  failed: Partial<Record<VectorLayerKey, boolean>>,
): VectorLayerKey[] {
  return (Object.keys(visibility) as VectorLayerKey[])
    .filter(key => visibility[key] && !loaded[key] && !loading[key] && !failed[key])
}

/** Put a freshly parsed layer on the globe: front and back in one synchronous step. */
function commitLayer(layerKey: VectorLayerKey, parsed: ParsedLayer, loadId: number, ctx: VectorRendererContext): void {
  const sceneData = ctx.sceneRef.current
  if (!sceneData) throw new Error(`${layerKey}: the scene is gone`)
  const { globe, camera, scene } = sceneData
  const config = LAYER_CONFIG[layerKey]
  const [frontRadius, backRadius] = layerRadii(layerKey)
  const visible = ctx.vectorLayersRef.current[layerKey]
  const backVisible = visible && !ctx.satelliteModeRef.current  // satellite is opaque: no back lines
  const fm = ctx.fadeManagerRef.current

  const frontMaterial = createFrontMaterial(config.color, 0)
  const backMaterial = createBackMaterial(config.color, 0)
  for (const material of [frontMaterial, backMaterial]) {
    material.uniforms.uCameraPos.value.copy(camera.position)
    ctx.shaderMaterialsRef.current.push(material)
  }
  const front = new THREE.LineSegments(segmentGeometry(parsed.positions[0], frontRadius), frontMaterial)
  front.visible = visible
  front.renderOrder = 10
  const back = new THREE.LineSegments(segmentGeometry(parsed.positions[1], backRadius), backMaterial)
  back.visible = backVisible
  back.renderOrder = -10

  const oldFront = ctx.frontLineLayersRef.current[layerKey]
  const oldBack = ctx.backLineLayersRef.current[layerKey]
  globe.add(front)
  globe.add(back)
  ctx.frontLineLayersRef.current[layerKey] = [front]
  ctx.backLineLayersRef.current[layerKey] = [back]
  if (isGlobeLayerKey(layerKey)) ctx.globeLayerTiersRef.current[layerKey].committed = 'start'
  delete ctx.failedLayersRef.current[layerKey]
  ctx.setLayersLoaded(prev => ({ ...prev, [layerKey]: true }))
  ctx.setIsLoadingLayers(prev => ({ ...prev, [layerKey]: false }))

  if (oldFront.length > 0 || oldBack.length > 0) {
    // LOD reload: cross-fade, front and back alike (keys carry the load id so a quick second
    // reload cannot cancel the first one's clean-up)
    retireLines(`${layerKey}_lod_old_${loadId}`, oldFront, ctx, globe)
    if (visible) fm.fadeTo(layerKey, [frontMaterial], 1, { duration: 100 })
    retireLines(`${layerKey}_back_lod_old_${loadId}`, oldBack, ctx, globe)
    if (backVisible) fm.fadeTo(`${layerKey}_back`, [backMaterial], 1, { duration: 100 })
  } else {
    // First appearance - fade from 0 to 1 (same keys as the visibility effect)
    if (visible) fm.fadeTo(layerKey, [frontMaterial], 1)
    if (backVisible) fm.fadeTo(`${layerKey}_back`, [backMaterial], 1)
  }

  if ((layerKey === 'rivers' || layerKey === 'lakes') && parsed.labels) {
    addLineLabels(layerKey, parsed.labels, ctx, scene)
  }
  if (layerKey in POINT_LABELS && ctx.layerLabelsRef.current[layerKey].length === 0) {
    loadPointLabels(layerKey as PointLabelLayer, ctx).catch(err => {
      if (!ctx.signal.aborted) console.error(`[Vector layers] ${layerKey} labels failed to load:`, err)
    })
  }
}

/**
 * Load a layer at the current detail level (coastlines and borders: their start tier) and
 * show it. A newer call for the same layer supersedes this one. A failure is logged, marks the
 * layer failed, and for coastlines and borders is reported through ctx.onStartError; it is
 * never retried here. This function never rejects.
 */
export async function loadVectorLayer(layerKey: VectorLayerKey, ctx: VectorRendererContext): Promise<void> {
  if (!ctx.sceneRef.current) return
  const loadId = (ctx.layerLoadIdsRef.current[layerKey] ?? 0) + 1
  ctx.layerLoadIdsRef.current[layerKey] = loadId
  const isCurrent = () => ctx.layerLoadIdsRef.current[layerKey] === loadId
  ctx.setIsLoadingLayers(prev => ({ ...prev, [layerKey]: true }))
  const url = getLayerUrl(layerKey, ctx.detailLevelRef.current)
  try {
    const parsed = await (parsedLayerCache.get(url) ?? fetchAndParse(url, layerKey, ctx, ctx.signal))
    if (ctx.signal.aborted || !isCurrent()) return
    commitLayer(layerKey, parsed, loadId, ctx)
  } catch (err) {
    // The Globe unmounted: the load was cancelled, there is nothing to report
    if (ctx.signal.aborted) return
    console.error(`[Vector layers] ${layerKey} failed to load:`, err)
    // A newer load of this layer owns its state now
    if (!isCurrent()) return
    ctx.failedLayersRef.current[layerKey] = true
    ctx.setIsLoadingLayers(prev => ({ ...prev, [layerKey]: false }))
    if (isGlobeLayerKey(layerKey)) ctx.onStartError(layerKey, err)
  }
}

/**
 * Swap a coastline/border layer up to a higher tier in place. Resolves only once this tier (or
 * a higher one) is on the globe; never downgrades. A request for a tier that is on its way
 * joins that load; a tier that failed is never fetched again and rejects with its error. Each
 * tier stands alone: a hi-res load on its way or failed does not stand in for the detail tier.
 * Rejects with an AbortError when `signal` or the Globe aborts; that tier may be asked for again.
 * Rejects with an OfflineNotCachedError when app offline mode is on and no cache holds the file:
 * not now, not failed - the tier is marked deferred and may be asked for again.
 */
export async function upgradeLayerTier(
  layerKey: GlobeLayerKey,
  tier: UpgradeTier,
  ctx: VectorRendererContext,
  signal: AbortSignal,
): Promise<void> {
  const state = ctx.globeLayerTiersRef.current[layerKey]
  if (tierRank(state.committed) >= tierRank(tier)) return
  if (tier in state.failed) throw state.failed[tier]
  const running = state.inFlight[tier]
  if (running) return running
  if (ctx.frontLineLayersRef.current[layerKey].length === 0 || ctx.backLineLayersRef.current[layerKey].length === 0) {
    throw new Error(`${layerKey}: the ${tier} tier needs the start tier on the globe first`)
  }
  const load = loadTier(layerKey, tier, ctx, signal).finally(() => {
    delete state.inFlight[tier]
  })
  state.inFlight[tier] = load
  return load
}

async function loadTier(layerKey: GlobeLayerKey, tier: UpgradeTier, ctx: VectorRendererContext, signal: AbortSignal): Promise<void> {
  const state = ctx.globeLayerTiersRef.current[layerKey]
  const linked = linkSignals(signal, ctx.signal)
  let parsed: ParsedLayer
  try {
    parsed = await fetchAndParse(getGlobeLayerUrl(layerKey, tier), layerKey, ctx, linked.signal)
    throwIfAborted(linked.signal)
  } catch (err) {
    // Cancelled is not failed, nor is offline without a cached file: only a failure bars the
    // tier, and it ends a deferral, so a resume never asks for (and reports) the tier again
    if (err instanceof OfflineNotCachedError) state.deferred[tier] = true
    else if (!linked.signal.aborted) {
      state.failed[tier] = err
      delete state.deferred[tier]
    }
    throw err
  } finally {
    linked.release()
  }
  delete state.deferred[tier]
  // A higher tier landed while this one was on its way
  if (tierRank(state.committed) >= tierRank(tier)) return
  const [frontRadius, backRadius] = layerRadii(layerKey)
  swapGeometry(ctx.frontLineLayersRef.current[layerKey][0], parsed.positions[0], frontRadius)
  swapGeometry(ctx.backLineLayersRef.current[layerKey][0], parsed.positions[1], backRadius)
  state.committed = tier
}

/** The tier load, resolving without the tier when app offline mode deferred it (not failed). */
function unlessDeferred(load: Promise<void>): Promise<void> {
  return load.catch((err: unknown) => {
    if (!(err instanceof OfflineNotCachedError)) throw err
  })
}

/**
 * Background task `layers`: coastlines and borders to their detail tier. In app offline mode a
 * detail file no cache holds is left for later (upgradeLayerTier marks it deferred, as
 * preloadRiversLakes skips such files): not a task failure, and resumeDeferredGlobeLayers
 * loads it once offline mode is off. One layer's failure does not keep the next one coarse:
 * every key is tried, one after the other, and the task then rejects once with the first
 * failure (one bg:layers report); every later failure is logged here with its layer, since
 * the rejection does not carry it. An abort ends the task at once.
 */
export async function upgradeGlobeLayers(
  ctx: VectorRendererContext,
  signal: AbortSignal,
  keys: readonly GlobeLayerKey[] = GLOBE_LAYER_KEYS,
): Promise<void> {
  let firstFailure: { err: unknown } | null = null
  for (const key of keys) {
    try {
      await unlessDeferred(upgradeLayerTier(key, 'detail', ctx, signal))
    } catch (err) {
      if (signal.aborted || ctx.signal.aborted) throw err
      if (firstFailure) console.error(`[Vector layers] ${key} detail tier failed to load:`, err)
      else firstFailure = { err }
    }
  }
  if (firstFailure) throw firstFailure.err
}

/**
 * App offline mode is off: the detail tiers the `layers` task deferred. Null while offline
 * mode is on or nothing is deferred; otherwise the load, which rejects like the task would.
 */
export function resumeDeferredGlobeLayers(ctx: VectorRendererContext): Promise<void> | null {
  if (OfflineFetch.isOffline) return null
  const keys = GLOBE_LAYER_KEYS.filter(key => ctx.globeLayerTiersRef.current[key].deferred.detail)
  if (keys.length === 0) return null
  return upgradeGlobeLayers(ctx, ctx.signal, keys)
}

/**
 * The hi-res coastline (today's coast_hires) where the Three.js globe is the only view closer
 * than the Mapbox switch: Mapbox failed. Called on every camera change, so the gate is checked
 * before the context is built; returns the load when it starts one, null otherwise. An offline
 * start fails Mapbox too: a coast_hires no cache holds is deferred (the load resolves without
 * it, no failure), not asked for again while offline mode is on, and loaded by the first
 * close-zoom camera change after offline mode is off.
 */
export function ensureHiresCoastline(gate: HiresCoastlineGate, buildContext: () => VectorRendererContext): Promise<void> | null {
  if (gate.getMapboxState() !== 'failed' || gate.getCameraDistance() >= gate.switchDistance) return null
  const ctx = buildContext()
  const tiers = ctx.globeLayerTiersRef.current.coastlines
  if (tiers.committed === null || tiers.committed === 'hires' || tiers.inFlight.hires || 'hires' in tiers.failed) return null
  if (tiers.deferred.hires && OfflineFetch.isOffline) return null
  return unlessDeferred(upgradeLayerTier('coastlines', 'hires', ctx, ctx.signal))
}

/**
 * Background task `rivers_lakes`: parse the rivers and lakes files a toggle at the current zoom
 * would load (normally ne_110m, 38 kB each) into the parsed cache loadVectorLayer reads first.
 * Offline, only files that are already cached are touched. Rejects on the first failure.
 */
export async function preloadRiversLakes(ctx: VectorRendererContext, signal: AbortSignal): Promise<void> {
  for (const key of ['rivers', 'lakes'] as const) {
    const url = getLayerUrl(key, ctx.detailLevelRef.current)
    if (parsedLayerCache.has(url)) continue
    if (OfflineFetch.isOffline && !(await OfflineFetch.isCached(url))) continue
    const linked = linkSignals(signal, ctx.signal)
    const pending = fetchAndParse(url, key, ctx, linked.signal)
    parsedLayerCache.set(url, pending)
    pending.then(linked.release, () => {
      linked.release()
      // A failed parse is not cached: a later toggle fetches the file itself
      if (parsedLayerCache.get(url) === pending) parsedLayerCache.delete(url)
    })
    await pending
  }
}
