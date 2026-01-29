// =============================================================================
// GEO LABEL SYSTEM - Extracted from Globe.tsx
// Handles label preloading, collision detection, visibility management,
// fade animations, and the cuddle system for country-capital pairs.
// =============================================================================

import * as THREE from 'three'
import { offlineFetch } from '../../../services/OfflineFetch'
import {
  LABEL_STYLES,
  LABEL_BASE_SCALE,
  CUDDLE,
  GEO,
} from '../../../config/globeConstants'
import {
  createLabelTexture,
  createGlobeTangentLabel,
  fadeLabelIn,
  fadeLabelOut,
  type GlobeLabelMesh,
} from '../../../utils/LabelRenderer'
import { FadeManager } from '../../../utils/FadeManager'
import { type VectorLayerVisibility } from '../../../config/vectorLayers'

const EARTH_RADIUS_KM = GEO.EARTH_RADIUS_KM

// =============================================================================
// TYPE DEFINITIONS
// =============================================================================

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

// Globe-pinned labels - sprites with constant screen size
export interface GlobeLabel {
  label: GeoLabel
  mesh: GlobeLabelMesh  // Changed from sprite to mesh for globe-tangent labels
  position: THREE.Vector3
}

/**
 * Context interface containing all shared refs and state needed by the geo label system.
 * Each field corresponds to a ref or state value from Globe.tsx scope.
 */
export interface GeoLabelContext {
  // Scene
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

  // Label loading state
  labelsLoadedRef: React.MutableRefObject<boolean>
  labelsLoadingRef: React.MutableRefObject<boolean>
  totalLabelsCountRef: React.MutableRefObject<number>

  // Label data
  geoLabelsRef: React.MutableRefObject<GlobeLabel[]>
  allLabelMeshesRef: React.MutableRefObject<GlobeLabelMesh[]>

  // Layer labels (lakes, rivers, plates, glaciers, coral reefs)
  layerLabelsRef: React.MutableRefObject<Record<string, GlobeLabel[]>>

  // Visibility toggles
  geoLabelsVisibleRef: React.MutableRefObject<boolean>
  labelTypesVisibleRef: React.MutableRefObject<Record<string, boolean>>
  vectorLayersRef: React.MutableRefObject<VectorLayerVisibility>

  // Visibility tracking
  visibleLabelNamesRef: React.MutableRefObject<Set<string>>
  visibleAfterCollisionRef: React.MutableRefObject<Set<string>>
  labelVisibilityStateRef: React.MutableRefObject<Map<string, boolean>>
  lastCalculatedZoomRef: React.MutableRefObject<number>

  // Fade animations
  fadeManagerRef: React.MutableRefObject<FadeManager>

  // Cuddle system
  cuddleOffsetsRef: React.MutableRefObject<Map<string, THREE.Vector3>>

  // Zoom & scale
  zoomRef: React.MutableRefObject<number>
  kmPerPixelRef: React.MutableRefObject<number>

  // Empire labels
  empireLabelsRef: React.MutableRefObject<Record<string, GlobeLabelMesh | null>>
  visibleEmpiresRef: React.MutableRefObject<Set<string>>
  showEmpireLabelsRef: React.MutableRefObject<boolean>

  // Ancient cities
  ancientCitiesRef: React.MutableRefObject<Record<string, GlobeLabelMesh[]>>
  ancientCitiesDataRef: React.MutableRefObject<Record<string, Array<{ name: string; type: string }>>>
  showAncientCitiesRef: React.MutableRefObject<boolean>

  // Update ref & state setters
  updateGeoLabelsRef: React.MutableRefObject<(() => void) | null>
  setLabelsLoaded: (loaded: boolean) => void

  // WebGL context recovery
  needsLabelReloadRef: React.MutableRefObject<boolean>
  setLabelReloadTrigger: React.Dispatch<React.SetStateAction<number>>
}

// =============================================================================
// LABEL PRELOADING
// =============================================================================

/**
 * Loads labels from /data/labels.json and creates globe-tangent label meshes.
 * This is the async core of the useEffect that runs on sceneReady.
 *
 * Extracted from Globe.tsx lines ~2915-2974.
 */
export async function loadGeoLabels(ctx: GeoLabelContext): Promise<void> {
  if (!ctx.sceneRef.current) return

  const { scene } = ctx.sceneRef.current
  const startTime = performance.now()
  console.log('[Loading] Starting label creation...')

  const res = await offlineFetch('/data/labels.json')
  const data: { labels: GeoLabel[] } = await res.json()
  if (!ctx.sceneRef.current) return

  const labelsToLoad = data.labels.filter(l => l.type !== 'metropol' && l.type !== 'city')
  ctx.totalLabelsCountRef.current = labelsToLoad.length

  const createStart = performance.now()

  // Create all label textures directly
  for (const label of labelsToLoad) {
    const { texture, width, height } = createLabelTexture(label.name, label.type, label.national)
    const phi = (90 - label.lat) * Math.PI / 180
    const theta = (label.lng + 180) * Math.PI / 180
    const styleKey = (label.type === 'capital' && label.national) ? 'capitalNat' : label.type
    const style = LABEL_STYLES[styleKey] || LABEL_STYLES.country
    const LABEL_HEIGHT: Record<string, number> = {
      empire: 1.052, continent: 1.05, ocean: 1.04, country: 1.008,
      capitalNat: 1.006, sea: 1.0057, mountain: 1.0054, desert: 1.0051,
      capital: 1.005, lake: 1.0045, river: 1.0045,
    }
    const r = LABEL_HEIGHT[styleKey] ?? LABEL_HEIGHT[label.type] ?? 1.005 + (style.fontSize - 18) * (0.045 / 46)
    const position = new THREE.Vector3(
      -r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)
    )
    const baseScale = LABEL_BASE_SCALE[styleKey] ?? LABEL_BASE_SCALE[label.type] ?? 0.04
    const LABEL_RENDER_ORDER: Record<string, number> = {
      continent: 1100, ocean: 1090, country: 1075, capitalNat: 1075,
      sea: 1065, mountain: 1060, desert: 1055, capital: 1075,
    }

    const mesh = createGlobeTangentLabel(texture, position, baseScale, width / height, LABEL_RENDER_ORDER[styleKey] ?? 1000)
    mesh.visible = false
    scene.add(mesh)
    ctx.geoLabelsRef.current.push({ label, mesh, position })
    ctx.allLabelMeshesRef.current.push(mesh)
  }

  const createTime = performance.now() - createStart
  const totalTime = performance.now() - startTime
  console.log(`[Loading] Labels DONE: ${labelsToLoad.length} in ${totalTime.toFixed(0)}ms (create: ${createTime.toFixed(0)}ms)`)

  ctx.labelsLoadedRef.current = true
  ctx.setLabelsLoaded(true)
  if (ctx.geoLabelsVisibleRef.current) ctx.updateGeoLabelsRef.current?.()
}

// =============================================================================
// WEBGL CONTEXT RECOVERY
// =============================================================================

/**
 * Handles label recovery after WebGL context loss.
 * Disposes old label meshes, clears arrays, resets loading flags,
 * and triggers a label reload.
 *
 * Extracted from Globe.tsx lines ~2978-3016.
 */
export function handleLabelReload(ctx: GeoLabelContext): void {
  if (!ctx.sceneRef.current || !ctx.needsLabelReloadRef.current) return

  console.log('[Globe] Starting label recovery...')
  const { scene } = ctx.sceneRef.current

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

  ctx.geoLabelsRef.current.forEach(({ mesh }) => disposeLabelMesh(mesh))
  ctx.geoLabelsRef.current = []

  // Also dispose layer-based labels (lakes, rivers, plates, glaciers, coral reefs)
  Object.keys(ctx.layerLabelsRef.current).forEach(key => {
    ctx.layerLabelsRef.current[key as keyof typeof ctx.layerLabelsRef.current].forEach(({ mesh }) => disposeLabelMesh(mesh))
    ctx.layerLabelsRef.current[key as keyof typeof ctx.layerLabelsRef.current] = []
  })

  ctx.allLabelMeshesRef.current = []
  ctx.labelVisibilityStateRef.current.clear()

  // Reset loading flags so labels can be reloaded
  ctx.labelsLoadedRef.current = false
  ctx.labelsLoadingRef.current = false
  ctx.needsLabelReloadRef.current = false
  ctx.setLabelsLoaded(false)

  // Trigger reload by incrementing the trigger
  ctx.setLabelReloadTrigger(prev => prev + 1)
}

// =============================================================================
// LABEL TYPE PRIORITIES AND CONFIGURATION
// =============================================================================

// Priority for collision detection (higher = more important)
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

// Collision radius uses kmPerPixel for constant screen-space collision detection
// This matches the constant screen size behavior of labels
const COLLISION_MULTIPLIER = 1.2  // Slightly larger than visual for comfortable spacing

// Layer label mappings: vector layer key -> label type
const LAYER_LABEL_MAPPINGS: { layerKey: 'lakes' | 'rivers' | 'plateBoundaries' | 'glaciers' | 'coralReefs', labelType: string }[] = [
  { layerKey: 'lakes', labelType: 'lake' },
  { layerKey: 'rivers', labelType: 'river' },
  { layerKey: 'plateBoundaries', labelType: 'plate' },
  { layerKey: 'glaciers', labelType: 'glacier' },
  { layerKey: 'coralReefs', labelType: 'coralReef' },
]

// =============================================================================
// COLLISION DETECTION HELPERS
// =============================================================================

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

function getCollisionRadius(type: string, currentKmPerPixel: number): number {
  const baseScale = LABEL_BASE_SCALE[type] ?? 0.03
  // Continents: much smaller collision box (they shouldn't hide countries)
  // Lakes/Plates/Glaciers/Reefs: smaller collision box (shouldn't hide other features)
  const smallBoxTypes = ['continent', 'lake', 'plate', 'glacier', 'coralReef']
  const typeMultiplier = smallBoxTypes.includes(type) ? 0.3 : 1
  // Same formula as label scaling: baseScale * 800 = target pixels
  const targetPixels = baseScale * 800 * COLLISION_MULTIPLIER * typeMultiplier
  const kmSize = targetPixels * currentKmPerPixel
  return kmSize / EARTH_RADIUS_KM
}

// Collision layers - labels only collide within their own layer
// This allows different feature types to coexist without hiding each other
function getCollisionLayer(type: string): string {
  if (type === 'capital' || type === 'ancientCity') return 'settlements'
  if (type === 'empire') return 'empire'
  if (type === 'lake' || type === 'river') return 'water'  // Water labels in own layer (don't hide continents)
  return 'geographic' // continent, ocean, country, sea, mountain, desert
}

// =============================================================================
// UPDATE GEO LABELS - Main visibility/collision function
// =============================================================================

/**
 * Updates geographic label visibility based on zoom and camera direction.
 * Performs collision detection, manages fade animations, and implements
 * the cuddle system for country-capital label pairs.
 *
 * Extracted from Globe.tsx lines ~3031-3427 (the updateGeoLabels useCallback).
 */
export function updateGeoLabels(ctx: GeoLabelContext): void {
  if (!ctx.sceneRef.current) return

  const labels = ctx.geoLabelsRef.current
  if (labels.length === 0) return // No labels loaded yet

  const currentZoom = ctx.zoomRef.current

  // Fade out all labels if main toggle is off
  if (!ctx.geoLabelsVisibleRef.current) {
    const fm = ctx.fadeManagerRef.current
    const visibilityState = ctx.labelVisibilityStateRef.current
    labels.forEach(item => {
      const labelName = item.label.name
      if (visibilityState.get(labelName)) {
        visibilityState.set(labelName, false)
        fadeLabelOut(item.mesh, fm, `geo-${labelName}`)
      }
    })
    Object.values(ctx.layerLabelsRef.current).forEach(layerLabels => {
      layerLabels.forEach(item => {
        const labelName = item.label.name
        if (visibilityState.get(labelName)) {
          visibilityState.set(labelName, false)
          fadeLabelOut(item.mesh, fm, `geo-${labelName}`)
        }
      })
    })
    ctx.visibleLabelNamesRef.current.clear()
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
      if (!ctx.labelTypesVisibleRef.current['capital']) {
        continue
      }

      visibleLabels.add(label.name)
      continue
    }

    // Skip if type is disabled in UI toggles
    if (!ctx.labelTypesVisibleRef.current[type]) {
      continue
    }

    // Skip continent labels when zoomed in >= 26%
    if (type === 'continent' && currentZoom >= 26) {
      continue
    }

    visibleLabels.add(label.name)
  }

  // Add layer labels (lakes, rivers, plates, glaciers, coral reefs) if their layer is enabled
  for (const { layerKey, labelType } of LAYER_LABEL_MAPPINGS) {
    const layerLabels = ctx.layerLabelsRef.current[layerKey]
    if (!layerLabels) continue

    const layerVisible = ctx.vectorLayersRef.current[layerKey]
    const typeVisible = ctx.labelTypesVisibleRef.current[labelType]

    if (!layerVisible || !typeVisible) continue

    for (const item of layerLabels) {
      visibleLabels.add(item.label.name)
    }
  }

  // Store the set of all eligible labels
  ctx.visibleLabelNamesRef.current = visibleLabels

  // Collision detection using 3D globe positions (camera-independent)
  // This ensures labels don't change when rotating, only when zooming

  const currentKmPerPixel = ctx.kmPerPixelRef.current

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
      radius: getCollisionRadius(item.label.type, currentKmPerPixel) * aspectScale,
      aspect,
      isNationalCapital,
      country: item.label.country
    })
  }

  // Add layer labels (lakes, rivers, plates, glaciers, coral reefs) - if both layer AND label type are enabled
  for (const { layerKey, labelType } of LAYER_LABEL_MAPPINGS) {
    const layerLabels = ctx.layerLabelsRef.current[layerKey]
    if (!layerLabels) continue

    // Check both the vector layer visibility AND the label type toggle
    const layerVisible = ctx.vectorLayersRef.current[layerKey]
    const typeVisible = ctx.labelTypesVisibleRef.current[labelType]
    if (!layerVisible || !typeVisible) continue

    for (const item of layerLabels) {
      candidates.push({
        name: item.label.name,
        id: `${item.label.name}_${item.label.type}`,
        type: item.label.type,
        position: item.position.clone().normalize(),
        priority: TYPE_PRIORITY[item.label.type] ?? 0,
        radius: getCollisionRadius(item.label.type, currentKmPerPixel),
        aspect: item.mesh.userData.aspect ?? 1
      })
      // Also ensure they're in visibleLabels for animation loop
      visibleLabels.add(item.label.name)
    }
  }

  // Add empire labels (highest priority) - only if empire is visible AND labels toggle is on
  Object.entries(ctx.empireLabelsRef.current).forEach(([empireId, mesh]) => {
    if (!mesh) return
    // Only add to collision if empire is visible AND empire labels toggle is on
    if (!ctx.visibleEmpiresRef.current.has(empireId)) return
    if (!ctx.showEmpireLabelsRef.current) return

    candidates.push({
      name: `empire_${empireId}`,
      id: `empire_${empireId}_empire`,
      type: 'empire',
      position: mesh.position.clone().normalize(),
      priority: TYPE_PRIORITY.empire,
      radius: getCollisionRadius('empire', currentKmPerPixel),
      aspect: (mesh as GlobeLabelMesh).userData?.aspect ?? 1
    })
  })

  // Add ancient cities (empire capitals) - high priority to override modern capitals
  // Priority: empire capital (500) > empire major city (400) > national capital (79)
  Object.entries(ctx.ancientCitiesRef.current).forEach(([empireId, meshes]) => {
    if (!meshes) return
    if (!ctx.visibleEmpiresRef.current.has(empireId)) return
    if (!ctx.showAncientCitiesRef.current) return

    const cityData = ctx.ancientCitiesDataRef.current[empireId] || []
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
        radius: getCollisionRadius('capitalNat', currentKmPerPixel),  // Same collision size as national capitals
        aspect: (mesh as GlobeLabelMesh).userData?.aspect ?? 1
      })
    })
  })

  // Sort by priority (highest first)
  candidates.sort((a, b) => b.priority - a.priority)

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

  // === CUDDLE SYSTEM: Country-Capital pairs ===
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

  ctx.cuddleOffsetsRef.current = newCuddleOffsets

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

  ctx.visibleAfterCollisionRef.current = visibleAfterCollision

  ctx.lastCalculatedZoomRef.current = currentZoom
}

// =============================================================================
// EMPIRE LABELS VISIBILITY
// =============================================================================

/**
 * Empire labels visibility function (called from animation loop).
 * Backside hiding is handled by the shader's vViewFade - we only manage
 * toggle/empire visibility here.
 *
 * Extracted from Globe.tsx lines ~3435-3497 (the updateEmpireLabelsVisibility useCallback).
 */
export function updateEmpireLabelsVisibility(
  _cameraDir: THREE.Vector3,
  ctx: {
    sceneRef: React.MutableRefObject<any>
    fadeManagerRef: React.MutableRefObject<FadeManager>
    labelVisibilityStateRef: React.MutableRefObject<Map<string, boolean>>
    empireLabelsRef: React.MutableRefObject<Record<string, GlobeLabelMesh | null>>
    showEmpireLabelsRef: React.MutableRefObject<boolean>
    visibleEmpiresRef: React.MutableRefObject<Set<string>>
    ancientCitiesRef: React.MutableRefObject<Record<string, GlobeLabelMesh[]>>
    showAncientCitiesRef: React.MutableRefObject<boolean>
    regionLabelsRef: React.MutableRefObject<Record<string, GlobeLabelMesh[]>>
  }
): void {
  if (!ctx.sceneRef.current) return

  const fm = ctx.fadeManagerRef.current
  const visibilityState = ctx.labelVisibilityStateRef.current

  // Empire name labels (renderOrder 1400) - using globe-tangent meshes with shader vViewFade
  Object.entries(ctx.empireLabelsRef.current).forEach(([empireId, mesh]) => {
    if (!mesh) return
    const shouldBeVisible = ctx.showEmpireLabelsRef.current && ctx.visibleEmpiresRef.current.has(empireId)
    const key = `empire-label-${empireId}`
    const isCurrentlyVisible = visibilityState.get(key) ?? false

    if (shouldBeVisible !== isCurrentlyVisible) {
      visibilityState.set(key, shouldBeVisible)
      if (shouldBeVisible) {
        fadeLabelIn(mesh, fm, key)
      } else {
        fadeLabelOut(mesh, fm, key)
      }
    }
  })

  // Ancient city markers via ref (capitals, major cities) - using globe-tangent meshes with shader vViewFade
  Object.entries(ctx.ancientCitiesRef.current).forEach(([empireId, meshes]) => {
    if (!meshes) return
    const shouldBeVisible = ctx.showAncientCitiesRef.current && ctx.visibleEmpiresRef.current.has(empireId)

    meshes.forEach((mesh, idx) => {
      const key = `city-${empireId}-${idx}`
      const isCurrentlyVisible = visibilityState.get(key) ?? false

      if (shouldBeVisible !== isCurrentlyVisible) {
        visibilityState.set(key, shouldBeVisible)
        if (shouldBeVisible) {
          fadeLabelIn(mesh, fm, key)
        } else {
          fadeLabelOut(mesh, fm, key)
        }
      }
    })
  })

  // Region labels - using globe-tangent meshes with shader vViewFade
  Object.entries(ctx.regionLabelsRef.current).forEach(([empireId, meshes]) => {
    if (!meshes) return
    const shouldBeVisible = ctx.showEmpireLabelsRef.current && ctx.visibleEmpiresRef.current.has(empireId)

    meshes.forEach((mesh, idx) => {
      const key = `region-${empireId}-${idx}`
      const isCurrentlyVisible = visibilityState.get(key) ?? false

      if (shouldBeVisible !== isCurrentlyVisible) {
        visibilityState.set(key, shouldBeVisible)
        if (shouldBeVisible) {
          fadeLabelIn(mesh, fm, key)
        } else {
          fadeLabelOut(mesh, fm, key)
        }
      }
    })
  })
}
