/**
 * Vector layer rendering functions.
 * Handles loading and rendering vector layers (coastlines, borders, rivers, lakes,
 * glaciers, coral reefs, tectonic plate boundaries) on both the front and back of the globe.
 */

import * as THREE from 'three'
import { LAYER_CONFIG, getLayerUrl, type VectorLayerKey, type VectorLayerVisibility } from '../../../config/vectorLayers'
import type { DetailLevel } from '../../../config/globeConstants'
import { LABEL_BASE_SCALE } from '../../../config/globeConstants'
import { offlineFetch } from '../../../services/OfflineFetch'
import { createFrontLineMaterial as createFrontMaterial, createBackLineMaterial as createBackMaterial } from '../../../shaders/globe'
import { createLabelTexture, createGlobeTangentLabel, type GlobeLabelMesh } from '../../../utils/LabelRenderer'
import { FadeManager } from '../../../utils/FadeManager'
import { isArtificialAntarcticBoundary } from '../../../utils/geoUtils'

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

/** Shared context required by the vector renderer functions. */
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

  loadingRef: React.MutableRefObject<Record<string, boolean>>
  shaderMaterialsRef: React.MutableRefObject<THREE.ShaderMaterial[]>
  frontLineLayersRef: React.MutableRefObject<Record<VectorLayerKey, THREE.Line[]>>
  backLineLayersRef: React.MutableRefObject<Record<VectorLayerKey, THREE.Line[]>>
  backLayersLoadedRef: React.MutableRefObject<Record<string, boolean>>
  fadeManagerRef: React.MutableRefObject<FadeManager>
  detailLevelRef: React.MutableRefObject<DetailLevel>
  layerLabelsRef: React.MutableRefObject<Record<string, GlobeLabel[]>>
  allLabelMeshesRef: React.MutableRefObject<GlobeLabelMesh[]>
  updateGeoLabelsRef: React.MutableRefObject<(() => void) | null>

  /** Current vector layer visibility state */
  vectorLayers: VectorLayerVisibility
  /** Current tile layer visibility state (satellite mode) */
  tileLayers: { satellite: boolean; streets: boolean }

  /** React state setters */
  setIsLoadingLayers: React.Dispatch<React.SetStateAction<Record<string, boolean>>>
  setLayersLoaded: React.Dispatch<React.SetStateAction<Record<string, boolean>>>

  /** Helper: convert lat/lng to 3D position on the globe */
  latLngTo3DRef: (lat: number, lng: number, r: number) => THREE.Vector3
}

/** Load FRONT layer (always high detail, visible on front of globe). */
export async function loadFrontLayer(
  layerKey: VectorLayerKey,
  ctx: VectorRendererContext
): Promise<void> {
  const {
    sceneRef,
    loadingRef,
    shaderMaterialsRef,
    frontLineLayersRef,
    fadeManagerRef,
    detailLevelRef,
    layerLabelsRef,
    allLabelMeshesRef,
    updateGeoLabelsRef,
    vectorLayers,
    setIsLoadingLayers,
    setLayersLoaded,
    latLngTo3DRef,
  } = ctx

  if (!sceneRef.current) return

  // Prevent duplicate loads
  const loadKey = `front_${layerKey}`
  if (loadingRef.current[loadKey]) return
  loadingRef.current[loadKey] = true

  const config = LAYER_CONFIG[layerKey]
  setIsLoadingLayers(prev => ({ ...prev, [layerKey]: true }))

  try {
    // Use LOD detail level for rivers/lakes, high for others
    const layerConfig = LAYER_CONFIG[layerKey]
    const detail = ('hasLOD' in layerConfig && layerConfig.hasLOD) ? detailLevelRef.current : 'high'
    const url = getLayerUrl(layerKey, detail)
    const response = await offlineFetch(url)
    const data = await response.json()

    // Store old lines for transition (may be undefined on first load)
    const oldLines = frontLineLayersRef.current[layerKey] ? [...frontLineLayersRef.current[layerKey]] : []
    const oldMaterials = oldLines.map(line => line.material as THREE.ShaderMaterial)

    // Create front material (visible on front of globe)
    const material = createFrontMaterial(config.color, 0)
    shaderMaterialsRef.current.push(material)
    if (sceneRef.current) {
      material.uniforms.uCameraPos.value.copy(sceneRef.current.camera.position)
    }

    const { globe } = sceneRef.current

    // Merge ALL features into ONE geometry for massive draw call reduction
    const allPositions: number[] = []

    // Process features in chunks to avoid blocking the main thread
    const features = data.features || []
    const CHUNK_SIZE = 500  // Process 500 features per frame
    let featureIndex = 0

    // Helper function to process a single feature
    const processFeature = (feature: any) => {
      const geometryType = feature.geometry.type
      let coordSets: number[][][] = []

      if (geometryType === 'LineString') {
        coordSets = [feature.geometry.coordinates]
      } else if (geometryType === 'MultiLineString') {
        coordSets = feature.geometry.coordinates
      } else if (geometryType === 'Polygon') {
        coordSets = feature.geometry.coordinates
      } else if (geometryType === 'MultiPolygon') {
        coordSets = feature.geometry.coordinates.flat()
      }

      coordSets.forEach((coords: number[][]) => {
        if (coords.length > 1) {
          // Filter out artificial Antarctic boundaries while preserving line continuity
          let segmentStarted = false
          for (let i = 0; i < coords.length; i++) {
            const coord = coords[i]
            const nextCoord = coords[i + 1]

            // Check if this segment should be skipped
            if (nextCoord && isArtificialAntarcticBoundary(coord, nextCoord)) {
              // End current segment if one was started
              if (segmentStarted) {
                allPositions.push(NaN, NaN, NaN)
                segmentStarted = false
              }
              continue
            }

            // Add vertex
            const point = latLngTo3DRef(coord[1], coord[0], config.radius)
            allPositions.push(point.x, point.y, point.z)
            segmentStarted = true
          }
          // Add NaN to create line break (visual separation between features)
          if (segmentStarted) {
            allPositions.push(NaN, NaN, NaN)
          }
        }
      })
    }

    // Function called when all chunks are processed
    const finishProcessing = () => {
      // Remove trailing NaN values to avoid computeBoundingSphere errors
      while (allPositions.length >= 3 && isNaN(allPositions[allPositions.length - 1])) {
        allPositions.pop()
        allPositions.pop()
        allPositions.pop()
      }

      // Create single merged geometry
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(allPositions, 3))
      // Set bounding sphere manually to avoid NaN issues from line breaks
      geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), config.radius + 0.01)
      const line = new THREE.Line(geometry, material)
      line.visible = vectorLayers[layerKey]
      line.renderOrder = 10
      globe.add(line)
      const lines = [line] // Single line object instead of thousands

      frontLineLayersRef.current[layerKey] = lines
      console.log(`[Loading] ${layerKey} DONE`)
      setLayersLoaded(prev => ({ ...prev, [layerKey]: true }))

      // Fade in immediately if layer is enabled (don't wait for visibility effect)
      // This fixes coral reefs/glaciers showing only on backside (front opacity stuck at 0)
      if (vectorLayers[layerKey]) {
        fadeManagerRef.current.fadeTo(`${layerKey}_front`, [material], 1)
      }

      // Extract labels for lakes and rivers (always high detail now)
      if ((layerKey === 'lakes' || layerKey === 'rivers') && sceneRef.current) {
        const { scene } = sceneRef.current
        const labelType = layerKey === 'lakes' ? 'lake' : 'river'

        // Track existing label names to avoid duplicates
        const existingNames = new Set(layerLabelsRef.current[layerKey].map(item => item.label.name))

        // Extract labels from features with names
        features.forEach((feature: any) => {
          const name = feature.properties?.name || feature.properties?.NAME
          if (!name) return

          // Skip if label already exists
          if (existingNames.has(name)) return

          // Get scalerank (used for sorting)
          const scalerank = feature.properties?.scalerank ?? feature.properties?.SCALERANK ?? 99

          // Calculate centroid from coordinates
          const geometryType = feature.geometry.type
          let allCoords: number[][] = []

          if (geometryType === 'LineString') {
            allCoords = feature.geometry.coordinates
          } else if (geometryType === 'MultiLineString') {
            allCoords = feature.geometry.coordinates.flat()
          } else if (geometryType === 'Polygon') {
            allCoords = feature.geometry.coordinates[0] // Outer ring
          } else if (geometryType === 'MultiPolygon') {
            allCoords = feature.geometry.coordinates.flat(2)
          }

          if (allCoords.length === 0) return

          // Calculate centroid
          let sumLng = 0, sumLat = 0
          allCoords.forEach((coord: number[]) => {
            sumLng += coord[0]
            sumLat += coord[1]
          })
          const centerLng = sumLng / allCoords.length
          const centerLat = sumLat / allCoords.length

          // Create globe-tangent label mesh
          const { texture, width, height } = createLabelTexture(name, labelType)

          // Position on globe
          const phi = (90 - centerLat) * Math.PI / 180
          const theta = (centerLng + 180) * Math.PI / 180
          const r = 1.0045
          const position = new THREE.Vector3(
            -r * Math.sin(phi) * Math.cos(theta),
            r * Math.cos(phi),
            r * Math.sin(phi) * Math.sin(theta)
          )

          const baseScale = LABEL_BASE_SCALE[labelType] ?? 0.04
          const aspect = width / height
          // Lake/river labels render BELOW continent/country labels
          const renderOrder = 950

          const mesh = createGlobeTangentLabel(texture, position, baseScale, aspect, renderOrder)
          mesh.visible = false

          scene.add(mesh)
          allLabelMeshesRef.current.push(mesh)

          const geoLabel: GeoLabel = {
            name,
            lat: centerLat,
            lng: centerLng,
            type: labelType,
            rank: scalerank,
            layerBased: true,
          }

          layerLabelsRef.current[layerKey].push({ label: geoLabel, mesh, position })
          existingNames.add(name)
        })

        // Trigger visibility update
        setTimeout(() => updateGeoLabelsRef.current?.(), 0)
      }

      // Load tectonic plate labels from separate file (pre-computed centroids)
      if (layerKey === 'plateBoundaries' && sceneRef.current) {
        const currentScene = sceneRef.current

        // Only load if not already loaded
        if (layerLabelsRef.current.plateBoundaries.length === 0) {
          offlineFetch('/data/layers/tectonic_plate_labels.geojson')
            .then(response => response.json())
            .then((labelsData: any) => {
              if (!currentScene) return

              const { scene } = currentScene

              labelsData.features.forEach((feature: any) => {
                const name = feature.properties?.name
                if (!name) return

                const [lng, lat] = feature.geometry.coordinates

                // Create globe-tangent label mesh
                const { texture, width, height } = createLabelTexture(name, 'plate')

                // Position on globe
                const phi = (90 - lat) * Math.PI / 180
                const theta = (lng + 180) * Math.PI / 180
                const r = 1.0045
                const position = new THREE.Vector3(
                  -r * Math.sin(phi) * Math.cos(theta),
                  r * Math.cos(phi),
                  r * Math.sin(phi) * Math.sin(theta)
                )

                const baseScale = 0.035 // Slightly smaller than ocean labels
                const aspect = width / height
                const renderOrder = 940 // Below lake/river labels

                const mesh = createGlobeTangentLabel(texture, position, baseScale, aspect, renderOrder)
                mesh.visible = false

                scene.add(mesh)
                allLabelMeshesRef.current.push(mesh)

                const geoLabel: GeoLabel = {
                  name,
                  lat,
                  lng,
                  type: 'plate',
                  rank: 1, // All plates have same priority
                  layerBased: true,
                }

                layerLabelsRef.current.plateBoundaries.push({ label: geoLabel, mesh, position })
              })

              console.log(`[Loading] Created ${layerLabelsRef.current.plateBoundaries.length} tectonic plate labels`)

              // Trigger visibility update
              setTimeout(() => updateGeoLabelsRef.current?.(), 0)
            })
            .catch(err => {
              console.error('[Loading] Failed to load plate labels:', err)
            })
        }
      }

      // Load glacier labels from separate file
      if (layerKey === 'glaciers' && sceneRef.current) {
        const currentScene = sceneRef.current

        // Only load if not already loaded
        if (layerLabelsRef.current.glaciers.length === 0) {
          offlineFetch('/data/layers/glacier_labels.geojson')
            .then(response => response.json())
            .then((labelsData: any) => {
              if (!currentScene) return

              const { scene } = currentScene

              labelsData.features.forEach((feature: any) => {
                const name = feature.properties?.name
                if (!name) return

                const [lng, lat] = feature.geometry.coordinates

                // Create globe-tangent label mesh
                const { texture, width, height } = createLabelTexture(name, 'glacier')

                // Position on globe
                const phi = (90 - lat) * Math.PI / 180
                const theta = (lng + 180) * Math.PI / 180
                const r = 1.0045
                const position = new THREE.Vector3(
                  -r * Math.sin(phi) * Math.cos(theta),
                  r * Math.cos(phi),
                  r * Math.sin(phi) * Math.sin(theta)
                )

                const baseScale = 0.032
                const aspect = width / height
                const renderOrder = 935

                const mesh = createGlobeTangentLabel(texture, position, baseScale, aspect, renderOrder)
                mesh.visible = false

                scene.add(mesh)
                allLabelMeshesRef.current.push(mesh)

                const geoLabel: GeoLabel = {
                  name,
                  lat,
                  lng,
                  type: 'glacier',
                  rank: 1,
                  layerBased: true,
                }

                layerLabelsRef.current.glaciers.push({ label: geoLabel, mesh, position })
              })

              console.log(`[Loading] Created ${layerLabelsRef.current.glaciers.length} glacier labels`)

              // Trigger visibility update
              setTimeout(() => updateGeoLabelsRef.current?.(), 0)
            })
            .catch(err => {
              console.error('[Loading] Failed to load glacier labels:', err)
            })
        }
      }

      // Load coral reef labels from separate file
      if (layerKey === 'coralReefs' && sceneRef.current) {
        const currentScene = sceneRef.current

        // Only load if not already loaded
        if (layerLabelsRef.current.coralReefs.length === 0) {
          offlineFetch('/data/layers/coral_reef_labels.geojson')
            .then(response => response.json())
            .then((labelsData: any) => {
              if (!currentScene) return

              const { scene } = currentScene

              labelsData.features.forEach((feature: any) => {
                const name = feature.properties?.name
                if (!name) return

                const [lng, lat] = feature.geometry.coordinates

                // Create globe-tangent label mesh
                const { texture, width, height } = createLabelTexture(name, 'coralReef')

                // Position on globe
                const phi = (90 - lat) * Math.PI / 180
                const theta = (lng + 180) * Math.PI / 180
                const r = 1.0045
                const position = new THREE.Vector3(
                  -r * Math.sin(phi) * Math.cos(theta),
                  r * Math.cos(phi),
                  r * Math.sin(phi) * Math.sin(theta)
                )

                const baseScale = 0.028
                const aspect = width / height
                const renderOrder = 930

                const mesh = createGlobeTangentLabel(texture, position, baseScale, aspect, renderOrder)
                mesh.visible = false

                scene.add(mesh)
                allLabelMeshesRef.current.push(mesh)

                const geoLabel: GeoLabel = {
                  name,
                  lat,
                  lng,
                  type: 'coralReef',
                  rank: 1,
                  layerBased: true,
                }

                layerLabelsRef.current.coralReefs.push({ label: geoLabel, mesh, position })
              })

              console.log(`[Loading] Created ${layerLabelsRef.current.coralReefs.length} coral reef labels`)

              // Trigger visibility update
              setTimeout(() => updateGeoLabelsRef.current?.(), 0)
            })
            .catch(err => {
              console.error('[Loading] Failed to load coral reef labels:', err)
            })
        }
      }

      // Use FadeManager for LOD transitions
      const fm = fadeManagerRef.current
      const globeRef = sceneRef.current!.globe

      if (oldLines.length > 0) {
        // Cross-fade: old fades out, new fades in
        // Use unique key for old material disposal
        fm.fadeTo(`${layerKey}_lod_old`, oldMaterials as THREE.Material[], 0, {
          duration: 100,
          onComplete: () => {
            oldMaterials.forEach(mat => {
              const idx = shaderMaterialsRef.current.indexOf(mat)
              if (idx !== -1) shaderMaterialsRef.current.splice(idx, 1)
            })
            oldLines.forEach(line => {
              globeRef.remove(line)
              line.geometry.dispose()
              ;(line.material as THREE.Material).dispose()
            })
          }
        })
        // Use same key as visibility effect so they don't conflict
        material.uniforms.uOpacity.value = 0
        fm.fadeTo(layerKey, [material], 1, { duration: 100 })
      } else {
        // Fresh load - fade from 0 to 1 (use same key as visibility effect)
        material.uniforms.uOpacity.value = 0
        fm.fadeTo(layerKey, [material], 1)
      }

      // Clean up loading state after finish
      loadingRef.current[`front_${layerKey}`] = false
      setIsLoadingLayers(prev => ({ ...prev, [layerKey]: false }))
    }

    // Process features in chunks using requestAnimationFrame
    const processChunk = () => {
      const endIndex = Math.min(featureIndex + CHUNK_SIZE, features.length)

      for (let i = featureIndex; i < endIndex; i++) {
        processFeature(features[i])
      }

      featureIndex = endIndex

      if (featureIndex < features.length) {
        // More work to do - yield to animation loop for smooth rendering
        requestAnimationFrame(processChunk)
      } else {
        // All features processed - create geometry and finish
        finishProcessing()
      }
    }

    // Start chunked processing
    processChunk()
  } catch (error) {
    console.error(`Failed to load front layer ${layerKey}:`, error)
    // Only clean up loading state on error (success cleanup is in finishProcessing)
    loadingRef.current[`front_${layerKey}`] = false
    setIsLoadingLayers(prev => ({ ...prev, [layerKey]: false }))
  }
}

/** Load BACK layer (same LOD as front, visible on back of globe). */
export async function loadBackLayer(
  layerKey: VectorLayerKey,
  ctx: VectorRendererContext,
  forceReload = false
): Promise<void> {
  const {
    sceneRef,
    loadingRef,
    shaderMaterialsRef,
    backLineLayersRef,
    backLayersLoadedRef,
    fadeManagerRef,
    detailLevelRef,
    vectorLayers,
    tileLayers,
    latLngTo3DRef,
  } = ctx

  if (!sceneRef.current) return
  if (backLayersLoadedRef.current[layerKey] && !forceReload) return // Already loaded

  const loadKey = `back_${layerKey}`
  if (loadingRef.current[loadKey]) return
  loadingRef.current[loadKey] = true

  const config = LAYER_CONFIG[layerKey]

  try {
    // Use same LOD as front layer for consistency
    const layerConfig = LAYER_CONFIG[layerKey]
    const detail = ('hasLOD' in layerConfig && layerConfig.hasLOD) ? detailLevelRef.current : 'high'
    const url = getLayerUrl(layerKey, detail)
    const response = await offlineFetch(url)
    const data = await response.json()

    if (!sceneRef.current) return

    // Clean up old back layer lines if reloading (for LOD changes)
    const oldLines = backLineLayersRef.current[layerKey]
    if (oldLines && oldLines.length > 0) {
      oldLines.forEach(line => {
        sceneRef.current?.globe.remove(line)
        line.geometry.dispose()
        if (line.material instanceof THREE.Material) {
          line.material.dispose()
        }
      })
      backLineLayersRef.current[layerKey] = []
    }

    // Create back material (visible on back of globe, dimmer)
    const material = createBackMaterial(config.color, 1)
    shaderMaterialsRef.current.push(material)
    material.uniforms.uCameraPos.value.copy(sceneRef.current.camera.position)

    const { globe } = sceneRef.current

    // Merge ALL features into ONE geometry for massive draw call reduction
    const allPositions: number[] = []
    const backRadius = config.radius - 0.001 // Slightly inside front layer

    // Process features in chunks to avoid blocking the main thread
    const features = data.features || []
    const CHUNK_SIZE = 500  // Process 500 features per frame
    let featureIndex = 0

    // Helper function to process a single feature
    const processFeature = (feature: any) => {
      const geometryType = feature.geometry.type
      let coordSets: number[][][] = []

      if (geometryType === 'LineString') {
        coordSets = [feature.geometry.coordinates]
      } else if (geometryType === 'MultiLineString') {
        coordSets = feature.geometry.coordinates
      } else if (geometryType === 'Polygon') {
        coordSets = feature.geometry.coordinates
      } else if (geometryType === 'MultiPolygon') {
        coordSets = feature.geometry.coordinates.flat()
      }

      coordSets.forEach((coords: number[][]) => {
        if (coords.length > 1) {
          // Filter out artificial Antarctic boundaries while preserving line continuity
          let segmentStarted = false
          for (let i = 0; i < coords.length; i++) {
            const coord = coords[i]
            const nextCoord = coords[i + 1]

            // Check if this segment should be skipped
            if (nextCoord && isArtificialAntarcticBoundary(coord, nextCoord)) {
              // End current segment if one was started
              if (segmentStarted) {
                allPositions.push(NaN, NaN, NaN)
                segmentStarted = false
              }
              continue
            }

            // Add vertex
            const point = latLngTo3DRef(coord[1], coord[0], backRadius)
            allPositions.push(point.x, point.y, point.z)
            segmentStarted = true
          }
          // Add NaN to create line break (visual separation between features)
          if (segmentStarted) {
            allPositions.push(NaN, NaN, NaN)
          }
        }
      })
    }

    // Function called when all chunks are processed
    const finishProcessing = () => {
      // Remove trailing NaN values to avoid computeBoundingSphere errors
      while (allPositions.length >= 3 && isNaN(allPositions[allPositions.length - 1])) {
        allPositions.pop()
        allPositions.pop()
        allPositions.pop()
      }

      // Create single merged geometry
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(allPositions, 3))
      // Set bounding sphere manually to avoid NaN issues from line breaks
      geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), backRadius + 0.01)
      const line = new THREE.Line(geometry, material)
      // Hide back lines in satellite mode (satellite is fully opaque)
      line.visible = vectorLayers[layerKey] && !tileLayers.satellite
      line.renderOrder = -10
      globe.add(line)
      const lines = [line] // Single line object instead of thousands

      backLineLayersRef.current[layerKey] = lines
      backLayersLoadedRef.current[layerKey] = true

      // Use FadeManager for fade-in (only if not in satellite mode)
      material.uniforms.uOpacity.value = 0
      if (!tileLayers.satellite) {
        fadeManagerRef.current.fadeTo(`${layerKey}_back`, [material], 1)
      }

      // Clean up loading state
      loadingRef.current[`back_${layerKey}`] = false
    }

    // Process features in chunks using requestAnimationFrame
    const processChunk = () => {
      const endIndex = Math.min(featureIndex + CHUNK_SIZE, features.length)

      for (let i = featureIndex; i < endIndex; i++) {
        processFeature(features[i])
      }

      featureIndex = endIndex

      if (featureIndex < features.length) {
        // More work to do - yield to animation loop for smooth rendering
        requestAnimationFrame(processChunk)
      } else {
        // All features processed - create geometry and finish
        finishProcessing()
      }
    }

    // Start chunked processing
    processChunk()
  } catch (error) {
    console.error(`Failed to load back layer ${layerKey}:`, error)
    // Only clean up loading state on error (success cleanup is in finishProcessing)
    loadingRef.current[`back_${layerKey}`] = false
  }
}
