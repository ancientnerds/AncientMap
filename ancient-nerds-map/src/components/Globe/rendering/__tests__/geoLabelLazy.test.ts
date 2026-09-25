/**
 * Geo labels on demand (U13). The start used to draw a 2D canvas with a
 * shadow for each of the 3,473 labels before globe_ready, 2,360 of them state
 * capitals the fade pass never shows. Now:
 * - only labels the fade pass can show, or that take part in its collision,
 *   become meshes;
 * - a mesh is created with its texture's size but without the texture and
 *   stays invisible until the show path draws the texture;
 * - labels that would be visible at load are textured before labelsLoaded;
 * - the show path draws at most a frame budget of textures per frame, so a
 *   zoom that reveals hundreds of labels never draws them in one task.
 * Node environment, the 2D canvas faked (labelTestCanvas).
 */

import * as THREE from 'three'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FadeManager } from '../../../../utils/FadeManager'
import {
  clearLabelTextureCache,
  fadeLabelIn,
  measureLabel,
  type GlobeLabelMesh,
} from '../../../../utils/LabelRenderer'
import { fakeGlyphs, stubLabelCanvas, type FakeLabelCanvas } from '../../../../utils/__tests__/labelTestCanvas'
import {
  applyGeoLabelFades,
  ensureLabelTexture,
  handleLabelReload,
  loadGeoLabels,
  selectGeoLabels,
  shownGeoLabels,
  type GeoLabel,
  type GeoLabelContext,
  type GlobeLabel,
} from '../geoLabelSystem'

const LABELS: GeoLabel[] = [
  { name: 'Europe', lat: 50, lng: 15, type: 'continent', rank: 1 },
  { name: 'Atlantic Ocean', lat: 30, lng: -40, type: 'ocean', rank: 1 },
  { name: 'Atlantic Ocean', lat: -20, lng: -15, type: 'ocean', rank: 1 },
  { name: 'Germany', lat: 51, lng: 10, type: 'country', rank: 2 },
  { name: 'Mali', lat: 17, lng: -4, type: 'country', rank: 2 },
  { name: 'Russia', lat: 60, lng: 90, type: 'country', rank: 2 },
  { name: 'Seychelles', lat: -4.6, lng: 55.5, type: 'country', rank: 5 },
  { name: 'Canada', lat: 60, lng: -100, type: 'country', rank: 2 },
  { name: 'Berlin', lat: 52.5, lng: 13.4, type: 'capital', rank: 3, national: true, country: 'Germany' },
  { name: 'Munich', lat: 48.1, lng: 11.6, type: 'capital', rank: 4, country: 'Germany' },
  { name: 'Kaliningrad', lat: 54.7, lng: 20.5, type: 'capital', rank: 4, country: 'Russia' },
  { name: 'Mali', lat: 13.5, lng: -7.5, type: 'capital', rank: 4, country: 'Mali' },
  { name: 'Victoria', lat: 48.4, lng: -123.4, type: 'capital', rank: 4, country: 'Canada' },
  { name: 'Victoria', lat: -4.6, lng: 55.5, type: 'capital', rank: 3, national: true, country: 'Seychelles' },
  { name: 'Hamburg', lat: 53.6, lng: 10, type: 'city', rank: 5 },
  { name: 'Ruhr', lat: 51.5, lng: 7.2, type: 'metropol', rank: 5 },
  { name: 'Alps', lat: 46.5, lng: 10, type: 'mountain', rank: 3 },
  { name: 'Kaliningrad', lat: 54.9, lng: 20, type: 'sea', rank: 5 },
]

const ALL_TYPES_ON = {
  continent: true, ocean: true, country: true, sea: true, mountain: true, desert: true, capital: true,
  lake: true, river: true, plate: true, glacier: true, coralReef: true,
}

function makeContext(overrides: { geoLabelsVisible?: boolean; setLabelsLoaded?: (loaded: boolean) => void } = {}) {
  const scene = new THREE.Scene()
  const ctx: GeoLabelContext = {
    sceneRef: { current: { scene } as unknown as NonNullable<GeoLabelContext['sceneRef']['current']> },
    labelsLoadedRef: { current: false },
    labelsLoadingRef: { current: true },
    totalLabelsCountRef: { current: 0 },
    geoLabelsRef: { current: [] },
    allLabelMeshesRef: { current: [] },
    layerLabelsRef: { current: {} },
    geoLabelsVisibleRef: { current: overrides.geoLabelsVisible ?? false },
    labelTypesVisibleRef: { current: { ...ALL_TYPES_ON } },
    vectorLayersRef: { current: {} as GeoLabelContext['vectorLayersRef']['current'] },
    visibleLabelNamesRef: { current: new Set() },
    visibleAfterCollisionRef: { current: new Set() },
    labelVisibilityStateRef: { current: new Map() },
    lastCalculatedZoomRef: { current: 0 },
    fadeManagerRef: { current: new FadeManager() },
    cuddleOffsetsRef: { current: new Map() },
    zoomRef: { current: 0 },
    // Tiny collision boxes: every eligible label survives the collision
    kmPerPixelRef: { current: 0.0001 },
    empireLabelsRef: { current: {} },
    visibleEmpiresRef: { current: new Set() },
    showEmpireLabelsRef: { current: false },
    ancientCitiesRef: { current: {} },
    ancientCitiesDataRef: { current: {} },
    showAncientCitiesRef: { current: false },
    setLabelsLoaded: overrides.setLabelsLoaded ?? vi.fn(),
    needsLabelReloadRef: { current: false },
    setLabelReloadTrigger: vi.fn(),
  }
  return { ctx, scene }
}

/** A camera that every fixture label but the southern Atlantic faces. */
const OVER_NORTH_POLE = new THREE.Vector3(0, 2.44, 0)

const textureOf = (mesh: THREE.Mesh) => (mesh.material as THREE.ShaderMaterial).uniforms.map.value as THREE.Texture | null
const drawnTexts = (canvases: FakeLabelCanvas[]) =>
  canvases.flatMap(c => c.context.drawn.filter(([method]) => method === 'fill').map(([, text]) => text))
const find = (ctx: GeoLabelContext, name: string, type: string) =>
  ctx.geoLabelsRef.current.find(item => item.label.name === name && item.label.type === type)!

let canvases: FakeLabelCanvas[]

beforeEach(() => {
  clearLabelTextureCache()
  fakeGlyphs.widthFactor = 1
  canvases = stubLabelCanvas()
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ labels: LABELS }))))
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1))
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
})

afterEach(() => {
  clearLabelTextureCache()
  fakeGlyphs.widthFactor = 1
  vi.unstubAllGlobals()
})

describe('selectGeoLabels', () => {
  it('keeps what the fade pass can show or collide with, in file order', () => {
    expect(selectGeoLabels(LABELS).map(l => `${l.type}:${l.name}`)).toEqual([
      'continent:Europe',
      'ocean:Atlantic Ocean',
      'ocean:Atlantic Ocean',
      'country:Germany',
      'country:Mali',
      'country:Russia',
      'country:Seychelles',
      'country:Canada',
      'capital:Berlin',
      // Munich (a state capital no other label names) is never shown and never collides
      // State capitals that share a name with a label the pass shows take part in it by that name
      'capital:Kaliningrad',
      'capital:Mali',
      'capital:Victoria',
      'capital:Victoria',
      'mountain:Alps',
      'sea:Kaliningrad',
    ])
  })
})

describe('shownGeoLabels', () => {
  it('is the first label of each name: the fade pass keys visibility by name', () => {
    const items = selectGeoLabels(LABELS).map(label => ({ label }) as GlobeLabel)
    expect(shownGeoLabels(items).map(i => `${i.label.type}:${i.label.name}`)).toEqual([
      'continent:Europe',
      'ocean:Atlantic Ocean',
      'country:Germany',
      'country:Mali',
      'country:Russia',
      'country:Seychelles',
      'country:Canada',
      'capital:Berlin',
      'capital:Kaliningrad',
      'capital:Victoria',
      'mountain:Alps',
    ])
  })
})

describe('loadGeoLabels', () => {
  it('creates every mesh at its texture size, without a texture and invisible', async () => {
    const { ctx, scene } = makeContext()
    await loadGeoLabels(ctx)

    expect(ctx.geoLabelsRef.current).toHaveLength(selectGeoLabels(LABELS).length)
    expect(ctx.allLabelMeshesRef.current).toHaveLength(ctx.geoLabelsRef.current.length)
    expect(scene.children).toHaveLength(ctx.geoLabelsRef.current.length)
    for (const { label, mesh } of ctx.geoLabelsRef.current) {
      const { width, height } = measureLabel(label.name, label.type, label.national)
      expect(mesh.userData.aspect).toBe(width / height)
      expect(textureOf(mesh)).toBeNull()
      expect(mesh.visible).toBe(false)
    }
    expect(drawnTexts(canvases)).toEqual([])
    expect(ctx.labelsLoadedRef.current).toBe(true)
    expect(ctx.setLabelsLoaded).toHaveBeenCalledWith(true)
  })

  it('textures every label the fade pass would show at load before labelsLoaded', async () => {
    let texturedAtLoaded: string[] | null = null
    const { ctx } = makeContext({
      geoLabelsVisible: true,
      setLabelsLoaded: () => {
        texturedAtLoaded = ctx.geoLabelsRef.current
          .filter(item => textureOf(item.mesh))
          .map(item => `${item.label.type}:${item.label.name}`)
      },
    })
    await loadGeoLabels(ctx)

    const visible = ctx.visibleAfterCollisionRef.current
    expect([...visible].sort()).toEqual(
      ['Atlantic Ocean', 'Berlin', 'Canada', 'Europe', 'Germany', 'Kaliningrad', 'Mali', 'Alps', 'Russia', 'Seychelles', 'Victoria'].sort(),
    )
    const expected = shownGeoLabels(ctx.geoLabelsRef.current)
      .filter(item => visible.has(item.label.name))
      .map(item => `${item.label.type}:${item.label.name}`)
    expect(texturedAtLoaded).toEqual(expected)

    // The first frame's fades then find every texture in place: nothing is drawn, nothing untextured shows
    const drawnBefore = drawnTexts(canvases).length
    applyGeoLabelFades(ctx, OVER_NORTH_POLE)
    expect(drawnTexts(canvases)).toHaveLength(drawnBefore)
    const shown = ctx.geoLabelsRef.current.filter(item => item.mesh.visible)
    expect(shown.map(item => `${item.label.type}:${item.label.name}`)).toEqual(expected)
    for (const item of shown) expect(textureOf(item.mesh)).not.toBeNull()
  })
})

describe('the show path', () => {
  it('draws a texture the first time a label shows, once', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    const germany = find(ctx, 'Germany', 'country')

    ctx.visibleAfterCollisionRef.current = new Set(['Germany'])
    applyGeoLabelFades(ctx, OVER_NORTH_POLE)
    expect(drawnTexts(canvases)).toEqual(['GERMANY'])
    expect(textureOf(germany.mesh)).not.toBeNull()
    expect(germany.mesh.visible).toBe(true)
    const texture = textureOf(germany.mesh)

    ctx.visibleAfterCollisionRef.current = new Set()
    applyGeoLabelFades(ctx, OVER_NORTH_POLE)
    ctx.visibleAfterCollisionRef.current = new Set(['Germany'])
    applyGeoLabelFades(ctx, OVER_NORTH_POLE)
    expect(drawnTexts(canvases)).toEqual(['GERMANY'])
    expect(textureOf(germany.mesh)).toBe(texture)
  })

  it('shows only the first label of a shared name and leaves the others without a texture', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    ctx.visibleAfterCollisionRef.current = new Set(['Mali', 'Victoria'])
    applyGeoLabelFades(ctx, OVER_NORTH_POLE)

    expect(find(ctx, 'Mali', 'country').mesh.visible).toBe(true)
    expect(textureOf(find(ctx, 'Mali', 'capital').mesh)).toBeNull()
    const victorias = ctx.geoLabelsRef.current.filter(item => item.label.name === 'Victoria')
    expect(victorias.map(item => item.mesh.visible)).toEqual([true, false])
    expect(textureOf(victorias[1].mesh)).toBeNull()
  })

  it('reuses the cached texture of a label with the same text and style', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    const [first, second] = ctx.geoLabelsRef.current.filter(item => item.label.name === 'Atlantic Ocean')
    ensureLabelTexture(first)
    ensureLabelTexture(second)
    expect(drawnTexts(canvases)).toEqual(['ATLANTIC OCEAN'])
    expect(textureOf(second.mesh)).toBe(textureOf(first.mesh))
  })

  it('sizes the mesh by the texture it drew when the font changed after the load', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    const alps = find(ctx, 'Alps', 'mountain')
    const atLoad = alps.mesh.userData.aspect
    fakeGlyphs.widthFactor = 1.25
    const { width, height } = measureLabel('Alps', 'mountain')
    ensureLabelTexture(alps)
    const canvas = (textureOf(alps.mesh) as THREE.CanvasTexture).image as { width: number; height: number }
    expect(alps.mesh.userData.aspect).not.toBe(atLoad)
    expect(alps.mesh.userData.aspect).toBe(width / height)
    expect(alps.mesh.userData.aspect).toBe(canvas.width / canvas.height)
  })

  it('refuses to show a label mesh that has no texture', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    const mesh = find(ctx, 'Europe', 'continent').mesh as GlobeLabelMesh
    expect(() => fadeLabelIn(mesh, ctx.fadeManagerRef.current, 'geo-Europe')).toThrow(/without its texture/)
    expect(mesh.visible).toBe(false)
  })
})

describe('context loss', () => {
  it('reloads the labels lazily the same way', async () => {
    const { ctx, scene } = makeContext({ geoLabelsVisible: true })
    await loadGeoLabels(ctx)
    ctx.needsLabelReloadRef.current = true
    handleLabelReload(ctx)
    expect(ctx.geoLabelsRef.current).toEqual([])
    expect(scene.children).toEqual([])
    expect(ctx.setLabelReloadTrigger).toHaveBeenCalledTimes(1)

    ctx.geoLabelsVisibleRef.current = false
    await loadGeoLabels(ctx)
    expect(ctx.geoLabelsRef.current).toHaveLength(selectGeoLabels(LABELS).length)
    for (const { mesh } of ctx.geoLabelsRef.current) {
      expect(textureOf(mesh)).toBeNull()
      expect(mesh.visible).toBe(false)
    }
  })
})

describe('the frame budget of the show path', () => {
  /** A clock that moves 3 ms per reading: with an 8 ms budget a frame draws three textures. */
  const steppingClock = () => {
    let t = 0
    return () => (t += 3)
  }
  const shownNames = (ctx: GeoLabelContext) =>
    ctx.geoLabelsRef.current.filter(item => item.mesh.visible).map(item => item.label.name)
  const above = (ctx: GeoLabelContext, name: string, type: string, distance = 2.44) =>
    find(ctx, name, type).position.clone().setLength(distance)

  it('draws a budget of textures per frame, the labels facing the camera first', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    ctx.visibleAfterCollisionRef.current = new Set(['Europe', 'Germany', 'Russia', 'Canada', 'Seychelles', 'Berlin', 'Alps'])
    const camera = above(ctx, 'Germany', 'country')
    const clock = steppingClock()

    applyGeoLabelFades(ctx, camera, clock, 8)
    expect(drawnTexts(canvases)).toEqual(['GERMANY', 'Berlin', 'EUROPE'])
    expect(shownNames(ctx).sort()).toEqual(['Berlin', 'Europe', 'Germany'])

    applyGeoLabelFades(ctx, camera, clock, 8)
    expect(drawnTexts(canvases).slice(3)).toEqual(['Alps', 'RUSSIA', 'CANADA'])
    applyGeoLabelFades(ctx, camera, clock, 8)
    expect(drawnTexts(canvases).slice(6)).toEqual(['SEYCHELLES'])
    expect(shownNames(ctx)).toHaveLength(7)
    // Nothing else was drawn or shown
    for (const item of ctx.geoLabelsRef.current) {
      if (!ctx.visibleAfterCollisionRef.current.has(item.label.name)) expect(textureOf(item.mesh)).toBeNull()
    }
  })

  it('leaves a label on the far side untextured until it turns toward the camera', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    ensureLabelTexture(find(ctx, 'Europe', 'continent'))
    ctx.visibleAfterCollisionRef.current = new Set(['Germany', 'Mali', 'Europe'])
    const farSide = above(ctx, 'Germany', 'country').negate()

    applyGeoLabelFades(ctx, farSide, steppingClock(), 8)
    applyGeoLabelFades(ctx, farSide, steppingClock(), 8)
    expect(drawnTexts(canvases)).toEqual(['EUROPE'])
    // A label that has its texture shows as before (the shader hides the far side)
    expect(shownNames(ctx)).toEqual(['Europe'])
    expect(ctx.labelVisibilityStateRef.current.get('Germany')).toBeUndefined()

    applyGeoLabelFades(ctx, above(ctx, 'Germany', 'country'), steppingClock(), 8)
    expect(shownNames(ctx).sort()).toEqual(['Europe', 'Germany', 'Mali'])
  })

  it('never shows another label of the same name while the first waits for its texture', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    // A layer label named like a waiting geo label: textured, but not the one the pass shows
    const lake = { label: { name: 'Victoria', lat: -1, lng: 33, type: 'lake', rank: 1 } as GeoLabel } as GlobeLabel
    lake.mesh = find(ctx, 'Berlin', 'capital').mesh.clone() as GlobeLabelMesh
    lake.mesh.material = (lake.mesh.material as THREE.ShaderMaterial).clone()
    ;(lake.mesh.material as THREE.ShaderMaterial).uniforms.map.value = new THREE.Texture()
    ctx.layerLabelsRef.current = { lakes: [lake] }
    ctx.visibleAfterCollisionRef.current = new Set(['Europe', 'Germany', 'Russia', 'Victoria'])
    const clock = steppingClock()

    applyGeoLabelFades(ctx, OVER_NORTH_POLE, clock, 8)
    const victorias = ctx.geoLabelsRef.current.filter(item => item.label.name === 'Victoria')
    expect(victorias.map(item => item.mesh.visible)).toEqual([false, false])
    expect(lake.mesh.visible).toBe(false)
    expect(ctx.labelVisibilityStateRef.current.get('Victoria')).toBeUndefined()

    applyGeoLabelFades(ctx, OVER_NORTH_POLE, clock, 8)
    expect(victorias.map(item => item.mesh.visible)).toEqual([true, false])
    expect(lake.mesh.visible).toBe(false)
  })

  it('hides and shows textured labels whatever the budget', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    for (const name of ['Europe', 'Germany', 'Russia', 'Canada']) ensureLabelTexture(shownGeoLabels(ctx.geoLabelsRef.current).find(i => i.label.name === name)!)
    ctx.visibleAfterCollisionRef.current = new Set(['Europe', 'Germany', 'Russia', 'Canada'])
    const spent = () => 1000 // every reading says the budget is gone

    applyGeoLabelFades(ctx, OVER_NORTH_POLE, spent, 8)
    expect(shownNames(ctx)).toEqual(['Europe', 'Germany', 'Russia', 'Canada'])

    ctx.visibleAfterCollisionRef.current = new Set(['Europe'])
    applyGeoLabelFades(ctx, OVER_NORTH_POLE, spent, 8)
    expect(['Germany', 'Russia', 'Canada'].map(n => ctx.labelVisibilityStateRef.current.get(n))).toEqual([false, false, false])
  })

  it('draws the first texture of a frame even when that one label is over the budget', async () => {
    const { ctx } = makeContext()
    await loadGeoLabels(ctx)
    ctx.visibleAfterCollisionRef.current = new Set(['Europe', 'Germany'])
    let t = 0
    const slow = () => (t += 50)
    applyGeoLabelFades(ctx, OVER_NORTH_POLE, slow, 8)
    expect(shownNames(ctx)).toEqual(['Germany'])
    applyGeoLabelFades(ctx, OVER_NORTH_POLE, slow, 8)
    expect(shownNames(ctx)).toEqual(['Europe', 'Germany'])
  })
})
