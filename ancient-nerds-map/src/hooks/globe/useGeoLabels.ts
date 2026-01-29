/**
 * useGeoLabels - Geographic label system for the globe
 *
 * Manages geographic labels (continents, oceans, countries, capitals, etc.)
 * including loading, collision detection, visibility, and the cuddle system
 * for country-capital label pairs.
 *
 * Extracted from Globe.tsx lines 3020-3424 (updateGeoLabels) and related code.
 */

import { useRef, useCallback, useEffect, useState } from 'react'
import * as THREE from 'three'
import {
  GEO,
  CUDDLE,
  LABEL_STYLES,
  LABEL_BASE_SCALE,
} from '../../config/globeConstants'
import {
  createLabelTexture,
  createGlobeTangentLabel,
  fadeLabelIn,
  fadeLabelOut,
  animateCuddleOffset,
  type GlobeLabelMesh,
} from '../../utils/LabelRenderer'
import { FadeManager } from '../../utils/FadeManager'
import { offlineFetch } from '../../services/OfflineFetch'
import type { LabelTypesVisible } from './useLabelVisibility'

const EARTH_RADIUS_KM = GEO.EARTH_RADIUS_KM

/**
 * Geographic label data structure (from labels.json)
 */
export interface GeoLabel {
  name: string
  lat: number
  lng: number
  type: 'continent' | 'country' | 'capital' | 'ocean' | 'sea' | 'region' | 'mountain' | 'desert' | 'lake' | 'river' | 'metropol' | 'city' | 'plate' | 'glacier' | 'coralReef'
  rank: number
  hidden?: boolean // Pre-computed collision: only show when zoomed in close
  layerBased?: boolean // True for labels extracted from vector layers (lakes, rivers)
  country?: string // Parent country name (for capitals - used to show capital when country is visible)
  national?: boolean // True for national capitals (ADM0CAP=1), false for state/regional capitals
  detailLevel?: number // LOD level this label came from (0=low, 1=medium, 2=high) - for lake/river sync
}

/**
 * Globe-pinned label with 3D mesh and position
 */
export interface GlobeLabel {
  label: GeoLabel
  mesh: GlobeLabelMesh
  position: THREE.Vector3
}

/**
 * Vector layer visibility state
 */
export type VectorLayerVisibility = {
  coastlines: boolean
  countryBorders: boolean
  rivers: boolean
  lakes: boolean
  plateBoundaries: boolean
  glaciers: boolean
  coralReefs: boolean
}

interface UseGeoLabelsOptions {
  scene: THREE.Scene | null
  geoLabelsVisible: boolean
  labelTypesVisible: LabelTypesVisible
  vectorLayers: VectorLayerVisibility
  zoom: number
  kmPerPixel: number
  showEmpireLabels: boolean
  visibleEmpires: Set<string>
  empireLabelsRef: React.MutableRefObject<Record<string, GlobeLabelMesh>>
  ancientCitiesRef: React.MutableRefObject<Record<string, GlobeLabelMesh[]>>
  ancientCitiesDataRef: React.MutableRefObject<Record<string, Array<{ name: string; lat: number; lng: number; years: number[]; type: string }>>>
  fadeManager: FadeManager
  onLabelsLoaded?: (count: number) => void
}

/**
 * Priority for collision detection (higher = more important)
 */
const TYPE_PRIORITY: Record<string, number> = {
  plate: 2000,    // Tectonic plates highest priority when enabled
  glacier: 1800,  // Glaciers high priority when enabled
  coralReef: 1800, // Coral reefs high priority when enabled
  empire: 1000,
  continent: 100, ocean: 90,
  country: 80,
  capitalNat: 79,  // National capitals just below countries
  sea: 75, mountain: 70, desert: 65,  // Geographic features
  lake: 50, river: 50,  // Water features below geographic labels
  capital: 40,  // State capitals/metropols
  city: 30
}

/**
 * Label height offsets (altitude above globe surface)
 */
const LABEL_HEIGHT: Record<string, number> = {
  empire: 1.052, continent: 1.05, ocean: 1.04, country: 1.008,
  capitalNat: 1.006, sea: 1.0057, mountain: 1.0054, desert: 1.0051,
  capital: 1.005, lake: 1.0045, river: 1.0045,
}

/**
 * Render order for different label types
 */
const LABEL_RENDER_ORDER: Record<string, number> = {
  continent: 1100, ocean: 1090, country: 1075, capitalNat: 1075,
  sea: 1065, mountain: 1060, desert: 1055, capital: 1075,
}

/**
 * Collision radius multiplier for comfortable spacing
 */
const COLLISION_MULTIPLIER = 1.2

export function useGeoLabels(options: UseGeoLabelsOptions) {
  const {
    scene,
    geoLabelsVisible,
    labelTypesVisible,
    vectorLayers,
    zoom,
    kmPerPixel,
    showEmpireLabels,
    visibleEmpires,
    empireLabelsRef,
    ancientCitiesRef,
    ancientCitiesDataRef,
    fadeManager,
    onLabelsLoaded,
  } = options

  // ========== Refs ==========

  // Main label storage
  const geoLabelsRef = useRef<GlobeLabel[]>([])

  // Track all globe-tangent label meshes for scale updates
  const allLabelMeshesRef = useRef<GlobeLabelMesh[]>([])

  // Layer-based labels (lakes, rivers, plates, glaciers, coral reefs)
  const layerLabelsRef = useRef<Record<string, GlobeLabel[]>>({
    lakes: [],
    rivers: [],
    plateBoundaries: [],
    glaciers: [],
    coralReefs: [],
  })

  // Cuddle system - track capital label offsets and animations
  const cuddleOffsetsRef = useRef<Map<string, THREE.Vector3>>(new Map())
  const cuddleAnimationsRef = useRef<Map<string, number>>(new Map())

  // Visibility tracking
  const visibleLabelNamesRef = useRef<Set<string>>(new Set())
  const visibleAfterCollisionRef = useRef<Set<string>>(new Set())
  const labelVisibilityStateRef = useRef<Map<string, boolean>>(new Map())
  const lastCalculatedZoomRef = useRef<number>(-1)

  // Loading state
  const labelsLoadedRef = useRef(false)
  const labelsLoadingRef = useRef(false)
  const [labelsLoaded, setLabelsLoaded] = useState(false)
  const [labelReloadTrigger, setLabelReloadTrigger] = useState(0)
  const totalLabelsCountRef = useRef(0)

  // Refs for current values (used in callbacks)
  const geoLabelsVisibleRef = useRef(geoLabelsVisible)
  geoLabelsVisibleRef.current = geoLabelsVisible
  const labelTypesVisibleRef = useRef(labelTypesVisible)
  labelTypesVisibleRef.current = labelTypesVisible
  const vectorLayersRef = useRef(vectorLayers)
  vectorLayersRef.current = vectorLayers
  const zoomRef = useRef(zoom)
  zoomRef.current = zoom
  const kmPerPixelRef = useRef(kmPerPixel)
  kmPerPixelRef.current = kmPerPixel
  const showEmpireLabelsRef = useRef(showEmpireLabels)
  showEmpireLabelsRef.current = showEmpireLabels
  const visibleEmpiresRef = useRef(visibleEmpires)
  visibleEmpiresRef.current = visibleEmpires

  // ========== Collision Detection Helper ==========

  const getCollisionRadius = useCallback((type: string) => {
    const baseScale = LABEL_BASE_SCALE[type] ?? 0.03
    // Continents: much smaller collision box (they shouldn't hide countries)
    // Lakes/Plates/Glaciers/Reefs: smaller collision box (shouldn't hide other features)
    const smallBoxTypes = ['continent', 'lake', 'plate', 'glacier', 'coralReef']
    const typeMultiplier = smallBoxTypes.includes(type) ? 0.3 : 1
    // Same formula as label scaling: baseScale * 800 = target pixels
    const targetPixels = baseScale * 800 * COLLISION_MULTIPLIER * typeMultiplier
    const kmSize = targetPixels * kmPerPixelRef.current
    return kmSize / EARTH_RADIUS_KM
  }, [])

  // ========== Update Label Visibility (copied exactly from Globe.tsx lines 3020-3416) ==========

  const updateGeoLabels = useCallback(() => {
    if (!scene) return

    const labels = geoLabelsRef.current
    if (labels.length === 0) return // No labels loaded yet

    const currentZoom = zoomRef.current
    const fm = fadeManager

    // Fade out all labels if main toggle is off
    if (!geoLabelsVisibleRef.current) {
      const visibilityState = labelVisibilityStateRef.current
      labels.forEach(item => {
        const labelName = item.label.name
        if (visibilityState.get(labelName)) {
          visibilityState.set(labelName, false)
          fadeLabelOut(item.mesh, fm, `geo-${labelName}`)
        }
      })
      Object.values(layerLabelsRef.current).forEach(layerLabels => {
        layerLabels.forEach(item => {
          const labelName = item.label.name
          if (visibilityState.get(labelName)) {
            visibilityState.set(labelName, false)
            fadeLabelOut(item.mesh, fm, `geo-${labelName}`)
          }
        })
      })
      visibleLabelNamesRef.current.clear()
      return
    }

    // ALL labels are eligible - only collision detection decides visibility
    const visibleLabels = new Set<string>()

    // Add all labels (only skip if type is disabled in UI)
    for (const item of labels) {
      const { label } = item
      const type = label.type

      // For capitals, only show national capitals (Berlin, Paris)
      if (type === 'capital') {
        const isNational = label.national === true

        // Skip non-national capitals (state/regional capitals)
        if (!isNational) {
          continue
        }

        // Skip if capital toggle is disabled
        if (!labelTypesVisibleRef.current['capital']) {
          continue
        }

        visibleLabels.add(label.name)
        continue
      }

      // Skip if type is disabled in UI toggles
      if (!labelTypesVisibleRef.current[type]) {
        continue
      }

      // Skip continent labels when zoomed in >= 26%
      if (type === 'continent' && currentZoom >= 26) {
        continue
      }

      visibleLabels.add(label.name)
    }

    // Add layer labels (lakes, rivers, plates, glaciers, coral reefs) if their layer is enabled
    const layerLabelMappings: { layerKey: 'lakes' | 'rivers' | 'plateBoundaries' | 'glaciers' | 'coralReefs', labelType: string }[] = [
      { layerKey: 'lakes', labelType: 'lake' },
      { layerKey: 'rivers', labelType: 'river' },
      { layerKey: 'plateBoundaries', labelType: 'plate' },
      { layerKey: 'glaciers', labelType: 'glacier' },
      { layerKey: 'coralReefs', labelType: 'coralReef' },
    ]

    for (const { layerKey, labelType } of layerLabelMappings) {
      const layerLabels = layerLabelsRef.current[layerKey]
      if (!layerLabels) continue

      const layerVisible = vectorLayersRef.current[layerKey]
      const typeVisible = labelTypesVisibleRef.current[labelType]

      if (!layerVisible || !typeVisible) continue

      for (const item of layerLabels) {
        visibleLabels.add(item.label.name)
      }
    }

    // Store the set of all eligible labels
    visibleLabelNamesRef.current = visibleLabels

    // ========== Collision Detection ==========
    // Using 3D globe positions (camera-independent)
    // This ensures labels don't change when rotating, only when zooming

    interface LabelCandidate {
      name: string
      id: string  // Unique identifier: name_type
      type: string
      position: THREE.Vector3
      priority: number
      radius: number
      aspect: number  // Width/height ratio for cuddle overlap detection
      isNationalCapital?: boolean
      country?: string
    }
    const candidates: LabelCandidate[] = []

    // Add geo labels
    for (const item of labels) {
      if (!visibleLabels.has(item.label.name)) continue

      // Use capitalNat for national capitals (higher priority than state capitals)
      const isNationalCapital = item.label.type === 'capital' && item.label.national
      const priorityType = isNationalCapital ? 'capitalNat' : item.label.type

      // Scale collision radius by aspect ratio for very long labels only
      // aspect = width/height, so long labels have aspect > 1
      const aspect = item.mesh.userData.aspect ?? 1
      const aspectScale = Math.min(2, Math.max(1, (aspect - 3) * 0.25 + 1))  // Only scale if aspect > 3, cap at 2x

      candidates.push({
        name: item.label.name,
        id: `${item.label.name}_${item.label.type}`,
        type: item.label.type,
        position: item.position.clone().normalize(),
        priority: TYPE_PRIORITY[priorityType] ?? 0,
        radius: getCollisionRadius(item.label.type) * aspectScale,
        aspect,
        isNationalCapital,
        country: item.label.country
      })
    }

    // Add layer labels (lakes, rivers, plates, glaciers, coral reefs) - if both layer AND label type are enabled
    for (const { layerKey, labelType } of layerLabelMappings) {
      const layerLabels = layerLabelsRef.current[layerKey]
      if (!layerLabels) continue

      // Check both the vector layer visibility AND the label type toggle
      const layerVisible = vectorLayersRef.current[layerKey]
      const typeVisible = labelTypesVisibleRef.current[labelType]
      if (!layerVisible || !typeVisible) continue

      for (const item of layerLabels) {
        candidates.push({
          name: item.label.name,
          id: `${item.label.name}_${item.label.type}`,
          type: item.label.type,
          position: item.position.clone().normalize(),
          priority: TYPE_PRIORITY[item.label.type] ?? 0,
          radius: getCollisionRadius(item.label.type),
          aspect: item.mesh.userData.aspect ?? 1
        })
        // Also ensure they're in visibleLabels for animation loop
        visibleLabels.add(item.label.name)
      }
    }

    // Add empire labels (highest priority) - only if empire is visible AND labels toggle is on
    Object.entries(empireLabelsRef.current).forEach(([empireId, mesh]) => {
      if (!mesh) return
      // Only add to collision if empire is visible AND empire labels toggle is on
      if (!visibleEmpiresRef.current.has(empireId)) return
      if (!showEmpireLabelsRef.current) return

      candidates.push({
        name: `empire_${empireId}`,
        id: `empire_${empireId}_empire`,
        type: 'empire',
        position: mesh.position.clone().normalize(),
        priority: TYPE_PRIORITY.empire,
        radius: getCollisionRadius('empire'),
        aspect: (mesh as GlobeLabelMesh).userData?.aspect ?? 1
      })
    })

    // Add ancient cities (empire capitals) - high priority to override modern capitals
    // Priority: empire capital (500) > empire major city (400) > national capital (79)
    Object.entries(ancientCitiesRef.current).forEach(([empireId, meshes]) => {
      if (!meshes) return
      if (!visibleEmpiresRef.current.has(empireId)) return
      if (!showEmpireLabelsRef.current) return  // Use same toggle as empire labels for cities

      const cityData = ancientCitiesDataRef.current[empireId] || []
      meshes.forEach((mesh, idx) => {
        const data = cityData[idx]
        if (!data) return

        // Empire capitals get priority 500, major cities get 400
        const isEmpireCapital = data.type === 'capital'
        const priority = isEmpireCapital ? 500 : 400

        candidates.push({
          name: `ancient_${empireId}_${data.name}`,
          id: `ancient_${empireId}_${data.name}_ancientCity`,
          type: 'ancientCity',
          position: mesh.position.clone().normalize(),
          priority,
          radius: getCollisionRadius('capitalNat'),  // Same collision size as national capitals
          aspect: (mesh as GlobeLabelMesh).userData?.aspect ?? 1
        })
      })
    })

    // Sort by priority (highest first)
    candidates.sort((a, b) => b.priority - a.priority)

    // Collision layers - labels only collide within their own layer
    // This allows different feature types to coexist without hiding each other
    const getCollisionLayer = (type: string): string => {
      if (type === 'capital' || type === 'ancientCity') return 'settlements'
      if (type === 'empire') return 'empire'
      if (type === 'lake' || type === 'river') return 'water'  // Water labels in own layer (don't hide continents)
      return 'geographic' // continent, ocean, country, sea, mountain, desert
    }

    // Group candidates by collision layer
    const layerGroups = new Map<string, typeof candidates>()
    for (const c of candidates) {
      const layer = getCollisionLayer(c.type)
      if (!layerGroups.has(layer)) layerGroups.set(layer, [])
      layerGroups.get(layer)!.push(c)
    }

    // Collision detection per layer - hide colliding labels based on priority
    const collidedSet = new Set<string>()
    const capitalToCountry = new Map<string, string>()

    for (const [_layer, group] of layerGroups) {
      // Already sorted by priority (highest first) from parent sort
      for (let i = 0; i < group.length; i++) {
        const a = group[i]
        if (collidedSet.has(a.id)) continue

        for (let j = i + 1; j < group.length; j++) {
          const b = group[j]
          if (collidedSet.has(b.id)) continue

          // Check angular distance on unit sphere
          const dot = a.position.dot(b.position)
          const angularDist = Math.acos(Math.min(1, Math.max(-1, dot)))
          const minDist = a.radius + b.radius

          if (angularDist < minDist) {
            // Regular collision - hide lower priority (b, since sorted)
            collidedSet.add(b.id)
          }
        }
      }
    }

    // ========== CUDDLE SYSTEM: Country-Capital pairs ==========
    // When a national capital overlaps with its own country, nudge the COUNTRY label away
    const newCuddleOffsets = new Map<string, THREE.Vector3>()

    // Find national capitals that overlap with their country (both visible)
    for (const cap of candidates) {
      // Only process national capitals that aren't already hidden by collision
      if (cap.type !== 'capital' || !cap.isNationalCapital || !cap.country || collidedSet.has(cap.id)) continue

      // Find matching country label
      const country = candidates.find(c =>
        c.type === 'country' && c.name === cap.country && !collidedSet.has(c.id)
      )
      if (!country) continue

      // Check overlap using bounding boxes instead of circular radius
      // Labels are rectangular, so we need to check actual box overlap on the tangent plane

      // Get label dimensions in angular units (radians on globe surface)
      // Use half the collision radius for tighter bounding boxes
      const capHeight = cap.radius
      const capWidth = capHeight * cap.aspect
      const countryHeight = country.radius
      const countryWidth = countryHeight * country.aspect

      // Project both positions onto tangent plane at midpoint for 2D box collision
      // Use country position as reference frame
      const normal = country.position.clone().normalize()

      // Create tangent plane basis vectors at country position
      const worldUp = new THREE.Vector3(0, 1, 0)
      let tangentX = new THREE.Vector3().crossVectors(worldUp, normal)
      if (tangentX.length() < 0.001) {
        tangentX.crossVectors(new THREE.Vector3(1, 0, 0), normal)
      }
      tangentX.normalize()
      const tangentY = new THREE.Vector3().crossVectors(normal, tangentX).normalize()

      // Project capital position onto tangent plane relative to country
      const capRelative = cap.position.clone().sub(country.position)
      const capX = capRelative.dot(tangentX)  // Horizontal offset
      const capY = capRelative.dot(tangentY)  // Vertical offset

      // Check bounding box overlap (country centered at origin, capital at capX, capY)
      // Box overlap: |centerA - centerB| < (widthA + widthB) / 2 for both axes
      const overlapX = Math.abs(capX) < (capWidth + countryWidth) / 2
      const overlapY = Math.abs(capY) < (capHeight + countryHeight) / 2

      if (overlapX && overlapY) {
        // Calculate how much overlap there is in each axis
        const overlapAmountX = (capWidth + countryWidth) / 2 - Math.abs(capX)
        const overlapAmountY = (capHeight + countryHeight) / 2 - Math.abs(capY)

        // Push in the direction of minimum overlap (easier to separate)
        // Use the tangent plane basis vectors we already computed
        let pushDir: THREE.Vector3
        let overlapAmount: number

        if (overlapAmountX < overlapAmountY) {
          // Push horizontally (along tangentX) - AWAY from capital
          // If capital is to the right (capX > 0), push country LEFT (-1)
          // If capital is to the left (capX < 0), push country RIGHT (+1)
          pushDir = tangentX.clone().multiplyScalar(capX > 0 ? -1 : 1)
          overlapAmount = overlapAmountX
        } else {
          // Push vertically (along tangentY) - AWAY from capital
          // If capital is above (capY > 0), push country DOWN (-1)
          // If capital is below (capY < 0), push country UP (+1)
          pushDir = tangentY.clone().multiplyScalar(capY > 0 ? -1 : 1)
          overlapAmount = overlapAmountY
        }

        // Max offset = 0.3 * country label height in angular units
        const maxOffset = CUDDLE.MAX_OFFSET_FACTOR * countryHeight

        // Displacement = min(overlap, max allowed)
        const offset = Math.min(overlapAmount * 1.1, maxOffset)  // 1.1x to fully separate

        // Store by COUNTRY name (the country label will move)
        newCuddleOffsets.set(country.name, pushDir.multiplyScalar(offset))
      }
    }

    cuddleOffsetsRef.current = newCuddleOffsets

    // Build visible set (not collided) and track capital-country relationships
    const visibleAfterCollision = new Set<string>()
    for (const c of candidates) {
      if (!collidedSet.has(c.id)) {
        visibleAfterCollision.add(c.name)

        // Track all capital labels for country dependency check
        if (c.type === 'capital' && c.country) {
          capitalToCountry.set(c.name, c.country)
        }
      }
    }

    // Post-collision filter: all capitals only visible if their country label is visible
    for (const [capitalName, countryName] of capitalToCountry) {
      if (!visibleAfterCollision.has(countryName)) {
        visibleAfterCollision.delete(capitalName)
      }
    }

    visibleAfterCollisionRef.current = visibleAfterCollision

    lastCalculatedZoomRef.current = currentZoom
  }, [scene, fadeManager, getCollisionRadius])

  // ========== Label Loading ==========

  useEffect(() => {
    if (!scene || labelsLoadedRef.current || labelsLoadingRef.current) return

    labelsLoadingRef.current = true
    const startTime = performance.now()
    console.log('[GeoLabels] Starting label creation...')

    const loadLabels = async () => {
      const res = await offlineFetch('/data/labels.json')
      const data: { labels: GeoLabel[] } = await res.json()
      if (!scene) return

      const labelsToLoad = data.labels.filter(l => l.type !== 'metropol' && l.type !== 'city')
      totalLabelsCountRef.current = labelsToLoad.length

      const createStart = performance.now()

      // Create all label textures directly
      for (const label of labelsToLoad) {
        const { texture, width, height } = createLabelTexture(label.name, label.type, label.national)
        const phi = (90 - label.lat) * Math.PI / 180
        const theta = (label.lng + 180) * Math.PI / 180
        const styleKey = (label.type === 'capital' && label.national) ? 'capitalNat' : label.type
        const style = LABEL_STYLES[styleKey] || LABEL_STYLES.country
        const r = LABEL_HEIGHT[styleKey] ?? LABEL_HEIGHT[label.type] ?? 1.005 + (style.fontSize - 18) * (0.045 / 46)
        const position = new THREE.Vector3(
          -r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)
        )
        const baseScale = LABEL_BASE_SCALE[styleKey] ?? LABEL_BASE_SCALE[label.type] ?? 0.04

        const mesh = createGlobeTangentLabel(texture, position, baseScale, width / height, LABEL_RENDER_ORDER[styleKey] ?? 1000)
        mesh.visible = false
        scene.add(mesh)
        geoLabelsRef.current.push({ label, mesh, position })
        allLabelMeshesRef.current.push(mesh)
      }

      const createTime = performance.now() - createStart
      const totalTime = performance.now() - startTime
      console.log(`[GeoLabels] Labels DONE: ${labelsToLoad.length} in ${totalTime.toFixed(0)}ms (create: ${createTime.toFixed(0)}ms)`)

      labelsLoadedRef.current = true
      setLabelsLoaded(true)
      onLabelsLoaded?.(labelsToLoad.length)
      if (geoLabelsVisibleRef.current) updateGeoLabels()
    }

    loadLabels().catch((err) => {
      console.error('[GeoLabels] Labels error:', err)
      labelsLoadingRef.current = false
    })
  }, [scene, labelReloadTrigger, updateGeoLabels, onLabelsLoaded])

  // ========== WebGL Context Recovery ==========

  useEffect(() => {
    const handleLabelReload = () => {
      if (!scene) return

      console.log('[GeoLabels] Starting label recovery...')

      // Dispose old label meshes and clear arrays
      const disposeLabelMesh = (mesh: THREE.Mesh) => {
        scene.remove(mesh)
        if (mesh.geometry) mesh.geometry.dispose()
        if (mesh.material) {
          const mat = mesh.material as THREE.ShaderMaterial
          if (mat.uniforms?.map?.value) mat.uniforms.map.value.dispose()
          mat.dispose()
        }
      }

      geoLabelsRef.current.forEach(({ mesh }) => disposeLabelMesh(mesh))
      geoLabelsRef.current = []

      // Also dispose layer-based labels (lakes, rivers, plates, glaciers, coral reefs)
      Object.keys(layerLabelsRef.current).forEach(key => {
        layerLabelsRef.current[key as keyof typeof layerLabelsRef.current].forEach(({ mesh }) => disposeLabelMesh(mesh))
        layerLabelsRef.current[key as keyof typeof layerLabelsRef.current] = []
      })

      allLabelMeshesRef.current = []
      labelVisibilityStateRef.current.clear()

      // Reset loading flags so labels can be reloaded
      labelsLoadedRef.current = false
      labelsLoadingRef.current = false
      setLabelsLoaded(false)

      // Trigger reload by incrementing the trigger
      setLabelReloadTrigger(prev => prev + 1)
    }

    window.addEventListener('webgl-labels-need-reload', handleLabelReload)
    return () => window.removeEventListener('webgl-labels-need-reload', handleLabelReload)
  }, [scene])

  // ========== Update on visibility change ==========

  useEffect(() => {
    if (geoLabelsVisible && labelsLoadedRef.current) updateGeoLabels()
  }, [geoLabelsVisible, updateGeoLabels])

  // ========== Update on zoom changes (throttled) ==========

  useEffect(() => {
    // Throttle zoom-based updates - only recalculate if zoom changed significantly
    if (Math.abs(zoom - lastCalculatedZoomRef.current) < 1) return

    if (geoLabelsVisible && labelsLoadedRef.current) {
      updateGeoLabels()
    }
  }, [zoom, geoLabelsVisible, updateGeoLabels])

  // ========== Update on label type/layer visibility changes (immediate) ==========

  useEffect(() => {
    if (geoLabelsVisible && labelsLoadedRef.current) {
      updateGeoLabels()
    }
  }, [labelTypesVisible, vectorLayers, showEmpireLabels, visibleEmpires, geoLabelsVisible, updateGeoLabels])

  // ========== Add Layer Label Helper ==========

  const addLayerLabel = useCallback((
    layerKey: 'lakes' | 'rivers' | 'plateBoundaries' | 'glaciers' | 'coralReefs',
    label: GeoLabel,
    mesh: GlobeLabelMesh,
    position: THREE.Vector3
  ) => {
    if (!layerLabelsRef.current[layerKey]) {
      layerLabelsRef.current[layerKey] = []
    }
    layerLabelsRef.current[layerKey].push({ label, mesh, position })
    allLabelMeshesRef.current.push(mesh)

    // Trigger update after adding
    setTimeout(() => updateGeoLabels(), 0)
  }, [updateGeoLabels])

  // ========== Clear Layer Labels Helper ==========

  const clearLayerLabels = useCallback((layerKey: 'lakes' | 'rivers' | 'plateBoundaries' | 'glaciers' | 'coralReefs') => {
    if (!scene) return

    const labels = layerLabelsRef.current[layerKey]
    if (labels) {
      labels.forEach(({ mesh }) => {
        scene.remove(mesh)
        if (mesh.geometry) mesh.geometry.dispose()
        if (mesh.material) {
          const mat = mesh.material as THREE.ShaderMaterial
          if (mat.uniforms?.map?.value) mat.uniforms.map.value.dispose()
          mat.dispose()
        }
      })
      layerLabelsRef.current[layerKey] = []
    }
  }, [scene])

  // ========== Return ==========

  return {
    // Main label storage
    geoLabelsRef,
    allLabelMeshesRef,
    layerLabelsRef,

    // Cuddle system
    cuddleOffsetsRef,
    cuddleAnimationsRef,

    // Visibility tracking
    visibleLabelNamesRef,
    visibleAfterCollisionRef,
    labelVisibilityStateRef,
    lastCalculatedZoomRef,

    // Loading state
    labelsLoaded,
    totalLabelsCount: totalLabelsCountRef.current,

    // Methods
    updateGeoLabels,
    addLayerLabel,
    clearLayerLabels,

    // Fade animation helpers (re-exported for animation loop)
    fadeLabelIn,
    fadeLabelOut,
    animateCuddleOffset,
  }
}
