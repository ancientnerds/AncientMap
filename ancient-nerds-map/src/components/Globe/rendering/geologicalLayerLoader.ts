/**
 * Geological Layer Loader Module
 *
 * Handles loading and rendering of geological overlay GeoJSON layers
 * (North Sea palaeolandscape data from Unpath'd Waters, CC BY 4.0).
 *
 * Supports LineString, MultiLineString, Polygon, MultiPolygon, Point, MultiPoint.
 * Points are rendered as small cross markers to stay in the THREE.Line pipeline.
 */

import * as THREE from 'three'
import { offlineFetch } from '../../../services/OfflineFetch'
import { createFrontLineMaterial as createFrontMaterial } from '../../../shaders/globe'
import type { FadeManager } from '../../../utils/FadeManager'
import { GEOLOGICAL_LAYER_CONFIG, getGeologicalLayerUrl, type GeologicalLayerKey } from '../../../config/geologicalLayers'

// ============================================================================
// Types
// ============================================================================

export interface GeologicalLayerContext {
  sceneRef: React.MutableRefObject<{
    globe: THREE.Mesh
    camera: THREE.PerspectiveCamera
  } | null>
  shaderMaterialsRef: React.MutableRefObject<THREE.ShaderMaterial[]>
  geologicalLinesRef: React.MutableRefObject<Record<string, THREE.Line[]>>
  geologicalCacheRef: React.MutableRefObject<Map<string, Float32Array>>
  geologicalLoadIdsRef: React.MutableRefObject<Record<string, number>>
  geologicalGeoJSONRef: React.MutableRefObject<Record<string, any>>
  fadeManagerRef: React.MutableRefObject<FadeManager>
  setIsLoadingGeological: (update: (prev: Partial<Record<GeologicalLayerKey, boolean>>) => Partial<Record<GeologicalLayerKey, boolean>>) => void
}

// ============================================================================
// Helpers
// ============================================================================

function latLngTo3DArray(lat: number, lng: number, r: number): [number, number, number] {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lng + 180) * Math.PI / 180
  return [
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  ]
}

/** Size of cross marker for point features, in degrees */
const CROSS_SIZE = 0.05

function pushCrossMarker(positions: number[], lat: number, lng: number, r: number): void {
  // Horizontal stroke
  const [x1, y1, z1] = latLngTo3DArray(lat, lng - CROSS_SIZE, r)
  const [x2, y2, z2] = latLngTo3DArray(lat, lng + CROSS_SIZE, r)
  positions.push(x1, y1, z1, x2, y2, z2, NaN, NaN, NaN)
  // Vertical stroke
  const [x3, y3, z3] = latLngTo3DArray(lat - CROSS_SIZE, lng, r)
  const [x4, y4, z4] = latLngTo3DArray(lat + CROSS_SIZE, lng, r)
  positions.push(x3, y3, z3, x4, y4, z4, NaN, NaN, NaN)
}

function pushLineCoords(positions: number[], coords: number[][], r: number): void {
  for (const coord of coords) {
    const [lon, lat] = coord
    const [x, y, z] = latLngTo3DArray(lat, lon, r)
    positions.push(x, y, z)
  }
  positions.push(NaN, NaN, NaN)
}

function pushPolygonCoords(positions: number[], rings: number[][][], r: number): void {
  // Render each ring (outer boundary + holes) as line loops
  for (const ring of rings) {
    pushLineCoords(positions, ring, r)
  }
}

// ============================================================================
// Main Loader
// ============================================================================

export async function loadGeologicalLayer(
  key: GeologicalLayerKey,
  ctx: GeologicalLayerContext,
  timeStepIndex?: number,
): Promise<void> {
  const {
    sceneRef,
    shaderMaterialsRef,
    geologicalCacheRef,
    geologicalLoadIdsRef,
    setIsLoadingGeological,
  } = ctx

  if (!sceneRef.current) return

  const config = GEOLOGICAL_LAYER_CONFIG[key]
  const radius = config.radius

  // Temporal layers bypass the in-memory positions cache — slice switches must
  // refetch GeoJSON so the Mapbox ref (geologicalGeoJSONRef, keyed by plain `key`)
  // stays in sync with whatever slice is currently active. Browser HTTP cache
  // makes repeat fetches cheap.
  const useCache = timeStepIndex === undefined

  // Track load ID for race condition prevention
  if (!geologicalLoadIdsRef.current[key]) geologicalLoadIdsRef.current[key] = 0
  geologicalLoadIdsRef.current[key]++
  const loadId = geologicalLoadIdsRef.current[key]

  setIsLoadingGeological(prev => ({ ...prev, [key]: true }))

  try {
    // Remove old lines for this layer
    disposeGeologicalLayerImmediate(key, ctx)

    // Create material
    const material = createFrontMaterial(config.color, 0)
    shaderMaterialsRef.current.push(material)
    if (sceneRef.current) {
      material.uniforms.uCameraPos.value.copy(sceneRef.current.camera.position)
    }

    // Check cache (static layers only)
    if (useCache) {
      const cached = geologicalCacheRef.current.get(key)
      if (cached) {
        if (loadId !== geologicalLoadIdsRef.current[key]) { material.dispose(); return }
        createAndAddLine(key, cached, material, radius, ctx)
        setIsLoadingGeological(prev => ({ ...prev, [key]: false }))
        return
      }
    }

    // Fetch GeoJSON
    const url = getGeologicalLayerUrl(key, timeStepIndex)
    let data: any
    try {
      const response = await offlineFetch(url)
      if (!response.ok) {
        console.warn(`Geological layer not found: ${key}`)
        setIsLoadingGeological(prev => ({ ...prev, [key]: false }))
        return
      }
      data = await response.json()
      // Store raw GeoJSON for Mapbox sync
      ctx.geologicalGeoJSONRef.current[key] = data
    } catch {
      console.warn(`Geological layer not available (offline): ${key}`)
      setIsLoadingGeological(prev => ({ ...prev, [key]: false }))
      return
    }

    const features = data.features || []
    const allPositions: number[] = []
    const CHUNK_SIZE = 500
    let featureIndex = 0

    const processChunk = () => {
      const endIndex = Math.min(featureIndex + CHUNK_SIZE, features.length)

      for (let i = featureIndex; i < endIndex; i++) {
        const feature = features[i]
        const geom = feature.geometry
        if (!geom) continue

        switch (geom.type) {
          case 'Point':
            pushCrossMarker(allPositions, geom.coordinates[1], geom.coordinates[0], radius)
            break
          case 'MultiPoint':
            for (const coord of geom.coordinates) {
              pushCrossMarker(allPositions, coord[1], coord[0], radius)
            }
            break
          case 'LineString':
            if (geom.coordinates.length >= 2) pushLineCoords(allPositions, geom.coordinates, radius)
            break
          case 'MultiLineString':
            for (const line of geom.coordinates) {
              if (line.length >= 2) pushLineCoords(allPositions, line, radius)
            }
            break
          case 'Polygon':
            pushPolygonCoords(allPositions, geom.coordinates, radius)
            break
          case 'MultiPolygon':
            for (const polygon of geom.coordinates) {
              pushPolygonCoords(allPositions, polygon, radius)
            }
            break
        }
      }

      featureIndex = endIndex

      if (featureIndex < features.length) {
        requestAnimationFrame(processChunk)
      } else {
        // Remove trailing NaN
        while (allPositions.length >= 3 && isNaN(allPositions[allPositions.length - 1])) {
          allPositions.pop(); allPositions.pop(); allPositions.pop()
        }

        if (loadId !== geologicalLoadIdsRef.current[key]) { material.dispose(); return }

        if (allPositions.length > 0 && sceneRef.current) {
          const positionsArray = new Float32Array(allPositions)
          if (useCache) geologicalCacheRef.current.set(key, positionsArray)
          createAndAddLine(key, positionsArray, material, radius, ctx)
        }
        setIsLoadingGeological(prev => ({ ...prev, [key]: false }))
      }
    }

    processChunk()
  } catch (error) {
    console.warn(`Failed to load geological layer ${key}:`, error)
    setIsLoadingGeological(prev => ({ ...prev, [key]: false }))
  }
}

// ============================================================================
// Geometry creation helper
// ============================================================================

function createAndAddLine(
  key: string,
  positions: Float32Array,
  material: THREE.ShaderMaterial,
  _radius: number,
  ctx: GeologicalLayerContext,
): void {
  const { sceneRef, geologicalLinesRef, fadeManagerRef } = ctx
  if (!sceneRef.current) return

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 1.003)
  const line = new THREE.Line(geometry, material)
  line.renderOrder = 5
  sceneRef.current.globe.add(line)

  if (!geologicalLinesRef.current[key]) geologicalLinesRef.current[key] = []
  geologicalLinesRef.current[key].push(line)

  material.uniforms.uOpacity.value = 0
  fadeManagerRef.current.fadeTo(`geological_${key}`, [material], 0.9)
}

// ============================================================================
// Dispose
// ============================================================================

/** Immediately remove lines (no fade) — used before reloading */
function disposeGeologicalLayerImmediate(key: string, ctx: GeologicalLayerContext): void {
  const lines = ctx.geologicalLinesRef.current[key] || []
  for (const line of lines) {
    ctx.sceneRef.current?.globe.remove(line)
    line.geometry.dispose()
    if (line.material instanceof THREE.Material) line.material.dispose()
  }
  ctx.geologicalLinesRef.current[key] = []
}

/** Fade out and dispose a single geological layer */
export function disposeGeologicalLayer(key: string, ctx: GeologicalLayerContext): void {
  const lines = ctx.geologicalLinesRef.current[key] || []
  delete ctx.geologicalGeoJSONRef.current[key]
  if (lines.length === 0) return

  ctx.geologicalLinesRef.current[key] = []
  const materials = lines.map(l => l.material as THREE.Material)
  ctx.fadeManagerRef.current.fadeTo(`geological_${key}`, materials, 0, {
    onComplete: () => {
      for (const line of lines) {
        ctx.sceneRef.current?.globe.remove(line)
        line.geometry.dispose()
        if (line.material instanceof THREE.Material) line.material.dispose()
      }
    },
  })
}

/** Dispose all geological layers */
export function disposeAllGeologicalLayers(ctx: GeologicalLayerContext): void {
  for (const key of Object.keys(ctx.geologicalLinesRef.current)) {
    disposeGeologicalLayer(key, ctx)
  }
}
