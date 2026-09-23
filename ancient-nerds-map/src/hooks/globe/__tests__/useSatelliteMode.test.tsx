/**
 * useSatelliteMode forces the basemap visible once the start-tier gray is on
 * the GPU; the satellite texture loads in the background and must not be a
 * condition for it any more.
 *
 * @vitest-environment jsdom
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'
import * as THREE from 'three'

import { useSatelliteMode } from '../useSatelliteMode'
import type { GlobeRefs } from '../types'
import type { VectorLayerVisibility } from '../../../config/vectorLayers'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null

const LAYERS: VectorLayerVisibility = { coastlines: true, countryBorders: true, rivers: false, lakes: false, coralReefs: false, glaciers: false, plateBoundaries: false }

function makeRefs(texturesReady: boolean) {
  const material = () => new THREE.ShaderMaterial({ uniforms: { uUseSatellite: { value: false } } })
  const basemapMesh = new THREE.Mesh(new THREE.BufferGeometry(), material())
  basemapMesh.visible = false
  const globeMaterial = new THREE.MeshBasicMaterial({ opacity: 1 })
  const refs = {
    satelliteMode: { current: false },
    basemapMesh: { current: basemapMesh },
    basemapBackMesh: { current: new THREE.Mesh(new THREE.BufferGeometry(), material()) },
    basemapSectionMeshes: { current: [new THREE.Mesh(new THREE.BufferGeometry(), material())] },
    texturesReady: { current: texturesReady },
    backLineLayers: { current: {} },
    scene: { current: { scene: new THREE.Scene(), globe: new THREE.Mesh(new THREE.BufferGeometry(), globeMaterial), backPoints: null } },
    stars: { current: null },
  } as unknown as GlobeRefs
  return { refs, basemapMesh, globeMaterial }
}

function Harness({ refs, satellite }: { refs: GlobeRefs; satellite: boolean }) {
  useSatelliteMode({ refs, satellite, vectorLayers: LAYERS, showMapbox: false })
  return null
}

async function render(refs: GlobeRefs, satellite: boolean) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => { root!.render(<Harness refs={refs} satellite={satellite} />) })
}

afterEach(async () => {
  await act(async () => { root?.unmount() })
  root = null
  document.body.classList.remove('satellite-mode')
})

describe('useSatelliteMode', () => {
  it('shows the basemap once the gray is ready, without any satellite texture', async () => {
    const { refs, basemapMesh, globeMaterial } = makeRefs(true)
    await render(refs, false)
    expect(basemapMesh.visible).toBe(true)
    expect(globeMaterial.opacity).toBe(0)
  })

  it('leaves the basemap hidden before the gray is ready', async () => {
    const { refs, basemapMesh } = makeRefs(false)
    await render(refs, false)
    expect(basemapMesh.visible).toBe(false)
  })

  it('switches the shader to the satellite only when told to', async () => {
    const { refs, basemapMesh } = makeRefs(true)
    await render(refs, true)
    expect((basemapMesh.material as THREE.ShaderMaterial).uniforms.uUseSatellite.value).toBe(true)
    expect(refs.satelliteMode.current).toBe(true)
    expect(document.body.classList.contains('satellite-mode')).toBe(true)
  })
})
