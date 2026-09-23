/**
 * The texture hook over a duck-typed renderer: only the start-tier gray is on
 * the critical path, a failure reaches onStartError instead of counting as
 * loaded, the satellite loads on request and waits for its texture, and a
 * context restore brings the start tier back.
 *
 * @vitest-environment jsdom
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as THREE from 'three'

vi.mock('../../../analytics/globeBackground', () => ({ trackBackgroundFailure: vi.fn() }))

import { trackBackgroundFailure } from '../../../analytics/globeBackground'
import { useTextureLoading } from '../useTextureLoading'
import type { GlobeRefs } from '../types'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

type Result = ReturnType<typeof useTextureLoading>

interface Bitmap { width: number; height: number; close: ReturnType<typeof vi.fn> }

const SIZES: Record<string, [number, number]> = {
  low: [4096, 2048],
  med: [8192, 4096],
  high: [16383, 8192],
}

let root: Root | null = null
let latest: Result
let fetched: string[]
let bitmaps: Map<string, Bitmap>
let failing: Set<string>
let holds: Map<string, Promise<void>>

function material(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({ uniforms: { uGrayBasemap: { value: null }, uSatellite: { value: null }, uUseSatellite: { value: false } } })
}

function makeRefs(maxTextureSize = 16384) {
  const mesh = () => new THREE.Mesh(new THREE.BufferGeometry(), material())
  const canvas = document.createElement('canvas')
  const renderer = {
    capabilities: { maxTextureSize },
    domElement: canvas,
    initTexture: vi.fn(),
    copyTextureToTexture: vi.fn(),
    getContext: () => ({ getError: () => 0, OUT_OF_MEMORY: 0x0505 }),
    render: vi.fn(),
  }
  const basemapMesh = mesh()
  const refs = {
    scene: { current: { renderer, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(), globe: new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial()) } },
    basemapMesh: { current: basemapMesh },
    basemapBackMesh: { current: mesh() },
    basemapSectionMeshes: { current: [mesh(), mesh(), mesh(), mesh()] },
    backgroundLoadingComplete: { current: false },
    texturesReady: { current: false },
  } as unknown as GlobeRefs
  const materials = () => [refs.basemapMesh.current!, ...refs.basemapSectionMeshes.current, refs.basemapBackMesh.current!]
    .map(m => m.material as THREE.ShaderMaterial)
  return { refs, renderer, canvas, materials }
}

interface Props {
  refs: GlobeRefs
  sceneReady: boolean
  satelliteRequested: boolean
  onStartError: (phase: string, err: unknown) => void
  onSatelliteFailed: () => void
}

function Harness(props: Props) {
  latest = useTextureLoading(props)
  return null
}

async function render(props: Props): Promise<void> {
  if (!root) {
    const container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  }
  await act(async () => { root!.render(<Harness {...props} />) })
}

/** Lets the stubbed fetch/decode chain and the frames settle inside act(). */
async function settle(): Promise<void> {
  for (let i = 0; i < 40; i++) {
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
  }
}

beforeEach(() => {
  fetched = []
  bitmaps = new Map()
  failing = new Set()
  holds = new Map()
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    fetched.push(url)
    if (failing.has(url)) return new Response('missing', { status: 404 })
    return new Response(url)
  }))
  vi.stubGlobal('createImageBitmap', vi.fn(async (blob: Blob) => {
    const url = await blob.text()
    const hold = holds.get(url)
    if (hold) await hold
    const tier = /_(low|med|high)\.webp$/.exec(url)![1]
    const [width, height] = SIZES[tier]
    const bitmap = { width, height, close: vi.fn() }
    bitmaps.set(url, bitmap)
    return bitmap
  }))
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0) as unknown as number)
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id))
  // jsdom: 1024x768, DPR 1 -> start tier low; desktop UA + 16384 GPU -> max tier high
  Object.defineProperty(window, 'devicePixelRatio', { value: 1, configurable: true })
  vi.mocked(trackBackgroundFailure).mockClear()
})

afterEach(async () => {
  await act(async () => { root?.unmount() })
  root = null
  vi.unstubAllGlobals()
})

const GRAY_LOW = '/data/basemaps/gray_dark_low.webp'
const GRAY_HIGH = '/data/basemaps/gray_dark_high.webp'
const SAT_LOW = '/data/basemaps/satellite_low.webp'
const SAT_HIGH = '/data/basemaps/satellite_high.webp'

function props(refs: GlobeRefs, over: Partial<Props> = {}): Props {
  return { refs, sceneReady: true, satelliteRequested: false, onStartError: vi.fn(), onSatelliteFailed: vi.fn(), ...over }
}

describe('useTextureLoading', () => {
  it('puts only the start-tier gray on the critical path', async () => {
    const { refs, materials, renderer } = makeRefs()
    const p = props(refs)
    await render(p)
    await settle()
    expect(fetched).toEqual([GRAY_LOW])
    expect(latest.texturesReady).toBe(true)
    expect(latest.backgroundLoadingComplete).toBe(true)
    expect(refs.backgroundLoadingComplete.current).toBe(true)
    expect(latest.satelliteReady).toBe(false)
    const tex = materials()[0].uniforms.uGrayBasemap.value as THREE.Texture
    expect(tex).toBeInstanceOf(THREE.Texture)
    expect(materials().every(m => m.uniforms.uGrayBasemap.value === tex)).toBe(true)
    expect(materials().every(m => m.uniforms.uSatellite.value === null)).toBe(true)
    expect(renderer.initTexture).toHaveBeenCalledWith(tex)
    expect(latest.basemapPlan).toEqual({ preloadSatellite: true, upgradeGray: true })
    expect(p.onStartError).not.toHaveBeenCalled()
  })

  it('waits for the scene', async () => {
    const { refs } = makeRefs()
    await render(props(refs, { sceneReady: false }))
    await settle()
    expect(fetched).toEqual([])
    expect(latest.basemapPlan).toBe(null)
    expect(latest.texturesReady).toBe(false)
  })

  it('reports a failed start gray once and never counts it as loaded', async () => {
    failing.add(GRAY_LOW)
    const { refs } = makeRefs()
    const p = props(refs)
    await render(p)
    await settle()
    expect(p.onStartError).toHaveBeenCalledTimes(1)
    expect(vi.mocked(p.onStartError).mock.calls[0][0]).toBe('basemap')
    expect(String(vi.mocked(p.onStartError).mock.calls[0][1])).toMatch(/gray_dark_low\.webp.*404/)
    expect(latest.texturesReady).toBe(false)
    expect(latest.backgroundLoadingComplete).toBe(false)
    expect(fetched).toEqual([GRAY_LOW])
  })

  it('plans no background work a device cannot use', async () => {
    const { refs } = makeRefs(8192) // GPU caps at med; start is low
    await render(props(refs))
    await settle()
    expect(latest.basemapPlan).toEqual({ preloadSatellite: false, upgradeGray: true })
  })

  it('runs the queue tasks: satellite at the start tier, gray at the maximum', async () => {
    const { refs, materials } = makeRefs()
    await render(props(refs))
    await settle()
    const ctrl = new AbortController()
    await act(async () => { await latest.loadSatellite(ctrl.signal) })
    expect(latest.satelliteReady).toBe(true)
    await act(async () => { await latest.upgradeGray(ctrl.signal) })
    expect(fetched).toEqual([GRAY_LOW, SAT_LOW, GRAY_HIGH])
    const sat = materials()[0].uniforms.uSatellite.value as THREE.Texture
    const gray = materials()[0].uniforms.uGrayBasemap.value as THREE.Texture
    expect((gray.image as { width: number }).width).toBe(16383)
    expect(materials().every(m => m.uniforms.uSatellite.value === sat && m.uniforms.uGrayBasemap.value === gray)).toBe(true)
  })

  it('loads the satellite on request, then its maximum tier while it stays on', async () => {
    const { refs, materials } = makeRefs()
    await render(props(refs))
    await settle()
    await act(async () => { latest.requestSatellite() })
    await render(props(refs, { satelliteRequested: true }))
    await settle()
    expect(fetched).toEqual([GRAY_LOW, SAT_LOW, SAT_HIGH])
    expect(latest.satelliteReady).toBe(true)
    const sat = materials()[0].uniforms.uSatellite.value as THREE.Texture
    expect((sat.image as { width: number }).width).toBe(16383)
  })

  it('does not upgrade the satellite while it is off', async () => {
    const { refs } = makeRefs()
    await render(props(refs))
    await settle()
    await act(async () => { await latest.loadSatellite(new AbortController().signal) })
    await settle()
    expect(fetched).toEqual([GRAY_LOW, SAT_LOW])
  })

  it('aborts the satellite upgrade when the satellite is switched off mid-upload', async () => {
    const { refs, materials } = makeRefs()
    await render(props(refs))
    await settle()
    await act(async () => { await latest.loadSatellite(new AbortController().signal) })
    const low = materials()[0].uniforms.uSatellite.value
    let release!: () => void
    holds.set(SAT_HIGH, new Promise<void>(r => { release = r }))
    await render(props(refs, { satelliteRequested: true }))
    await settle()
    await render(props(refs, { satelliteRequested: false }))
    release()
    await settle()
    expect(bitmaps.get(SAT_HIGH)!.close).toHaveBeenCalledTimes(1)
    expect(materials()[0].uniforms.uSatellite.value).toBe(low)
    expect(trackBackgroundFailure).not.toHaveBeenCalled()
  })

  it('ends the wait when the requested satellite fails, and reports it', async () => {
    failing.add(SAT_LOW)
    const { refs } = makeRefs()
    const p = props(refs)
    await render(p)
    await settle()
    await act(async () => { latest.requestSatellite() })
    await settle()
    expect(p.onSatelliteFailed).toHaveBeenCalledTimes(1)
    expect(trackBackgroundFailure).toHaveBeenCalledTimes(1)
    expect(vi.mocked(trackBackgroundFailure).mock.calls[0][0]).toBe('satellite')
    expect(latest.satelliteReady).toBe(false)
  })

  it('ends the wait when the queued satellite task fails, and leaves the report to the queue', async () => {
    failing.add(SAT_LOW)
    const { refs } = makeRefs()
    const p = props(refs)
    await render(p)
    await settle()
    let error: unknown = null
    await act(async () => { await latest.loadSatellite(new AbortController().signal).catch(e => { error = e }) })
    expect(String(error)).toMatch(/satellite_low\.webp.*404/)
    expect(p.onSatelliteFailed).toHaveBeenCalledTimes(1)
    expect(trackBackgroundFailure).not.toHaveBeenCalled()
  })

  it('reports nothing for a load cut short by the unmount', async () => {
    let release!: () => void
    holds.set(GRAY_LOW, new Promise<void>(r => { release = r }))
    const { refs } = makeRefs()
    const p = props(refs)
    await render(p)
    await settle()
    await act(async () => { root!.unmount() })
    root = null
    release()
    await settle()
    expect(p.onStartError).not.toHaveBeenCalled()
    expect(bitmaps.get(GRAY_LOW)!.close).toHaveBeenCalledTimes(1)
  })

  it('frees the textures and closes the kept bitmap on unmount', async () => {
    const { refs, materials } = makeRefs()
    await render(props(refs))
    await settle()
    await act(async () => { root!.unmount() })
    root = null
    expect(materials().every(m => m.uniforms.uGrayBasemap.value === null)).toBe(true)
    expect(bitmaps.get(GRAY_LOW)!.close).toHaveBeenCalledTimes(1)
  })

  it('hands a satellite load cut short by a context restore over to the restore, without a failure', async () => {
    const { refs, canvas } = makeRefs()
    const p = props(refs)
    await render(p)
    await settle()
    let release!: () => void
    holds.set(SAT_LOW, new Promise<void>(r => { release = r }))
    await act(async () => { latest.requestSatellite() })
    await render({ ...p, satelliteRequested: true })
    await settle()
    await act(async () => { canvas.dispatchEvent(new Event('webglcontextrestored')) })
    holds.delete(SAT_LOW)
    release()
    await settle()
    expect(p.onSatelliteFailed).not.toHaveBeenCalled()
    expect(trackBackgroundFailure).not.toHaveBeenCalled()
    expect(latest.satelliteReady).toBe(true)
  })

  it('brings the start tier back after a context restore and asks for the upgrades again', async () => {
    const { refs, canvas, materials } = makeRefs()
    await render(props(refs))
    await settle()
    const start = materials()[0].uniforms.uGrayBasemap.value
    await act(async () => { await latest.upgradeGray(new AbortController().signal) })
    await act(async () => { await latest.loadSatellite(new AbortController().signal) })
    expect(materials()[0].uniforms.uGrayBasemap.value).not.toBe(start)

    let releaseGray!: () => void
    let releaseSat!: () => void
    holds.set(GRAY_HIGH, new Promise<void>(r => { releaseGray = r }))
    holds.set(SAT_LOW, new Promise<void>(r => { releaseSat = r }))
    await act(async () => { canvas.dispatchEvent(new Event('webglcontextrestored')) })
    expect(materials()[0].uniforms.uGrayBasemap.value).toBe(start)
    expect(materials()[0].uniforms.uSatellite.value).toBe(null)
    expect(latest.satelliteReady).toBe(false)
    releaseGray()
    releaseSat()
    await settle()
    expect(fetched.filter(u => u === GRAY_HIGH)).toHaveLength(2)
    expect(fetched.filter(u => u === SAT_LOW)).toHaveLength(2)
    expect(latest.satelliteReady).toBe(true)
    expect((materials()[0].uniforms.uGrayBasemap.value.image as { width: number }).width).toBe(16383)
    expect(trackBackgroundFailure).not.toHaveBeenCalled()
  })
})
