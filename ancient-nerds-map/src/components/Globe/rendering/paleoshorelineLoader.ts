/**
 * Paleoshoreline Loader Module
 *
 * Handles loading and rendering of paleoshoreline contour lines that show
 * historic coastlines at different sea levels.
 *
 * Extracted from Globe.tsx to reduce file size and improve maintainability.
 */

import * as THREE from 'three'
import { offlineFetch } from '../../../services/OfflineFetch'
import { createFrontLineMaterial as createFrontMaterial } from '../../../shaders/globe'
import type { FadeManager } from '../../../utils/FadeManager'

// ============================================================================
// Types
// ============================================================================

export interface PaleoshorelineContext {
  sceneRef: React.MutableRefObject<{
    globe: THREE.Mesh
    camera: THREE.PerspectiveCamera
  } | null>
  shaderMaterialsRef: React.MutableRefObject<THREE.ShaderMaterial[]>
  paleoshorelineLinesRef: React.MutableRefObject<THREE.Line[]>
  paleoshorelinePositionsCacheRef: React.MutableRefObject<Map<string, Float32Array>>
  paleoshorelineLoadIdRef: React.MutableRefObject<number>
  fadeManagerRef: React.MutableRefObject<FadeManager>
  latLngTo3D: (lat: number, lng: number, r: number) => THREE.Vector3
  setIsLoadingPaleoshoreline: (loading: boolean) => void
  replaceCoastlines: boolean
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Convert lat/lng to 3D coordinates on a sphere
 */
function latLngTo3DArray(lat: number, lng: number, r: number): [number, number, number] {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lng + 180) * Math.PI / 180
  return [
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta)
  ]
}

// ============================================================================
// Main Loader Function
// ============================================================================

/**
 * Load paleoshoreline contour for a specific sea level
 *
 * @param level - Sea level in meters (negative = lower than current)
 * @param ctx - Loading context with refs and callbacks
 */
export async function loadPaleoshoreline(
  level: number,
  ctx: PaleoshorelineContext
): Promise<void> {
  const {
    sceneRef,
    shaderMaterialsRef,
    paleoshorelineLinesRef,
    paleoshorelinePositionsCacheRef,
    paleoshorelineLoadIdRef,
    fadeManagerRef,
    setIsLoadingPaleoshoreline,
    replaceCoastlines,
  } = ctx

  if (!sceneRef.current) return

  const scale = '50m' // Medium detail for better performance
  const cacheKey = `${level}_${scale}`

  // Increment load ID to track this load (prevents race conditions)
  paleoshorelineLoadIdRef.current++
  const loadId = paleoshorelineLoadIdRef.current

  setIsLoadingPaleoshoreline(true)

  try {
    // Remove old paleoshoreline lines first
    paleoshorelineLinesRef.current.forEach(line => {
      sceneRef.current?.globe.remove(line)
      line.geometry.dispose()
      if (line.material instanceof THREE.Material) {
        line.material.dispose()
      }
    })
    paleoshorelineLinesRef.current = []

    // Create material - use coastline color when replacing, sand color otherwise
    const color = replaceCoastlines ? 0x00e0d0 : 0xC2B280  // Teal or sandy beach
    const material = createFrontMaterial(color, 0)  // Start at 0 for fade in
    shaderMaterialsRef.current.push(material)
    if (sceneRef.current) {
      material.uniforms.uCameraPos.value.copy(sceneRef.current.camera.position)
    }

    // Check if we have cached processed positions (instant load)
    const cachedPositions = paleoshorelinePositionsCacheRef.current.get(cacheKey)
    if (cachedPositions) {
      // Check if this load is still the current one
      if (loadId !== paleoshorelineLoadIdRef.current) {
        material.dispose()
        return
      }
      // Instant load from cached positions
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(cachedPositions, 3))
      geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 1.003)
      const line = new THREE.Line(geometry, material)
      line.renderOrder = 5
      sceneRef.current.globe.add(line)
      paleoshorelineLinesRef.current = [line]
      material.uniforms.uOpacity.value = 0
      fadeManagerRef.current.fadeTo('paleoshoreline', [material], 0.9)
      setIsLoadingPaleoshoreline(false)
      return
    }

    // Load from server (or Service Worker cache if offline)
    const url = `/data/sea-levels/${level}m/contour_${scale}.json`
    let data: any
    try {
      const response = await offlineFetch(url)
      if (!response.ok) {
        console.warn(`Paleoshoreline data not found for ${level}m`)
        setIsLoadingPaleoshoreline(false)
        return
      }
      data = await response.json()
    } catch (e) {
      console.warn(`Paleoshoreline not available (offline): ${level}m`)
      setIsLoadingPaleoshoreline(false)
      return
    }

    const features = data.features || []
    const allPositions: number[] = []
    const CHUNK_SIZE = 500  // Process 500 features per frame
    let featureIndex = 0

    const processChunk = () => {
      const endIndex = Math.min(featureIndex + CHUNK_SIZE, features.length)

      for (let i = featureIndex; i < endIndex; i++) {
        const feature = features[i]
        const coords = feature.geometry?.coordinates
        if (!coords || coords.length < 2) continue

        for (const coord of coords) {
          const [lon, lat] = coord
          const [x, y, z] = latLngTo3DArray(lat, lon, 1.002)
          allPositions.push(x, y, z)
        }
        // NaN creates a line break
        allPositions.push(NaN, NaN, NaN)
      }

      featureIndex = endIndex

      if (featureIndex < features.length) {
        // More to process - schedule next chunk
        requestAnimationFrame(processChunk)
      } else {
        // Done - create geometry
        // Remove trailing NaN values to avoid computeBoundingSphere errors
        while (allPositions.length >= 3 && isNaN(allPositions[allPositions.length - 1])) {
          allPositions.pop()
          allPositions.pop()
          allPositions.pop()
        }

        // Check if this load is still the current one (prevents multiple shorelines)
        if (loadId !== paleoshorelineLoadIdRef.current) {
          material.dispose()
          return
        }

        if (allPositions.length > 0 && sceneRef.current) {
          // Cache the processed positions for instant future loads
          const positionsArray = new Float32Array(allPositions)
          paleoshorelinePositionsCacheRef.current.set(cacheKey, positionsArray)

          const geometry = new THREE.BufferGeometry()
          geometry.setAttribute('position', new THREE.Float32BufferAttribute(positionsArray, 3))
          geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 1.003)
          const line = new THREE.Line(geometry, material)
          line.renderOrder = 5
          sceneRef.current.globe.add(line)
          paleoshorelineLinesRef.current = [line]

          // Use FadeManager for fade-in (target opacity 0.9)
          material.uniforms.uOpacity.value = 0
          fadeManagerRef.current.fadeTo('paleoshoreline', [material], 0.9)
        }
        setIsLoadingPaleoshoreline(false)
      }
    }

    // Start processing
    processChunk()
    return  // Don't set loading to false yet - processChunk will do it

  } catch (error) {
    console.warn(`Failed to load paleoshoreline at ${level}m:`, error)
    setIsLoadingPaleoshoreline(false)
  }
}

/**
 * Dispose of paleoshoreline lines and fade out
 */
export function disposePaleoshoreline(
  paleoshorelineLinesRef: React.MutableRefObject<THREE.Line[]>,
  sceneRef: React.MutableRefObject<{ globe: THREE.Mesh } | null>,
  fadeManagerRef: React.MutableRefObject<FadeManager>
): void {
  if (paleoshorelineLinesRef.current.length === 0) return

  const lines = [...paleoshorelineLinesRef.current]
  paleoshorelineLinesRef.current = []  // Clear ref immediately to prevent double dispose

  const materials = lines.map(l => l.material as THREE.Material)
  fadeManagerRef.current.fadeTo('paleoshoreline', materials, 0, {
    onComplete: () => {
      lines.forEach(line => {
        sceneRef.current?.globe.remove(line)
        line.geometry.dispose()
        if (line.material instanceof THREE.Material) {
          line.material.dispose()
        }
      })
      // Keep positions cache for instant reload next time
    }
  })
}
