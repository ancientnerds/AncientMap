/**
 * empireRenderer.ts - Empire border rendering functions extracted from Globe.tsx
 *
 * All functions that were previously useCallback closures inside Globe.tsx are now
 * standalone functions that take an explicit GlobeRenderContext parameter containing
 * the shared refs and state they need.
 */

import * as THREE from 'three'
import { EMPIRES } from '../../../config/empireData'
import { LAYER_CONFIG } from '../../../config/vectorLayers'
import { offlineFetch } from '../../../services/OfflineFetch'
import { pointInGeoJSONGeometry } from '../../../utils/geometry'
import { formatYear, formatYearPeriod } from '../../../utils/geoUtils'
import { FadeManager } from '../../../utils/FadeManager'
import {
  createGlobeTangentLabel,
  fadeLabelIn,
  drawUnifiedLabel,
  type GlobeLabelMesh,
} from '../../../utils/LabelRenderer'
import {
  createFrontLineMaterial as createFrontMaterial,
  createBackLineMaterial as createBackMaterial,
  createStencilMaterial,
  createEmpireFillMaterial,
} from '../../../shaders/globe'
import { ATLAS_FONT_FAMILY } from '../../../config/globeConstants'

// Alias for backward compatibility (matches Globe.tsx)
const drawLabelWithShadow = drawUnifiedLabel

// =============================================================================
// TYPES
// =============================================================================

/** Scene refs structure matching Globe.tsx sceneRef.current */
export interface GlobeSceneRef {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  controls: any // OrbitControls
  points: THREE.Points | null
  backPoints: THREE.Points | null
  shadowPoints: THREE.Points | null
  globe: THREE.Mesh
}

/**
 * GlobeRenderContext - Contains all the shared refs and state that the empire
 * rendering functions access from Globe.tsx scope. Each function receives this
 * as an explicit parameter instead of closing over component state.
 */
export interface GlobeRenderContext {
  // Core scene ref
  sceneRef: React.MutableRefObject<GlobeSceneRef | null>

  // Shader materials tracking (for camera position updates in animation loop)
  shaderMaterialsRef: React.MutableRefObject<THREE.ShaderMaterial[]>

  // Empire 3D object refs
  empireBorderLinesRef: React.MutableRefObject<Record<string, THREE.Line[]>>
  empireLabelsRef: React.MutableRefObject<Record<string, GlobeLabelMesh>>
  regionLabelsRef: React.MutableRefObject<Record<string, GlobeLabelMesh[]>>
  ancientCitiesRef: React.MutableRefObject<Record<string, GlobeLabelMesh[]>>

  // All label meshes tracking (for scale updates, collision detection)
  allLabelMeshesRef: React.MutableRefObject<GlobeLabelMesh[]>

  // Label visibility state map (for fade in/out management)
  labelVisibilityStateRef: React.MutableRefObject<Map<string, boolean>>

  // Fade manager for animated opacity transitions
  fadeManagerRef: React.MutableRefObject<FadeManager>

  // Data cache refs
  regionDataRef: React.MutableRefObject<Record<string, Array<{ name: string; lat: number; lng: number; years: number[] }>> | null>
  ancientCitiesDataRef: React.MutableRefObject<Record<string, Array<{ name: string; lat: number; lng: number; years: number[]; type: string }>>>
  empirePolygonFeaturesRef: React.MutableRefObject<Record<string, Array<{ geometry: { type: string; coordinates: any } }>>>

  // Abort controllers for cancellation of pending loads
  empireLoadAbortRef: React.MutableRefObject<Record<string, AbortController>>

  // Visible empires ref (synced from state)
  visibleEmpiresRef: React.MutableRefObject<Set<string>>

  // Satellite mode ref (for back-line visibility)
  satelliteModeRef: React.MutableRefObject<boolean>

  // Empire years ref (synced from state, for onEmpireYearsChange callback)
  empireYearsRef: React.MutableRefObject<Record<string, number>>

  // Callback ref for syncing empire years to parent (called after polygon data loads)
  onEmpireYearsChangeRef: React.MutableRefObject<((years: Record<string, number>) => void) | undefined>

  // Ref to updateGeoLabels function (for re-running collision detection after label creation)
  updateGeoLabelsRef: React.MutableRefObject<(() => void) | null>

  // Debounce timers for label position updates (1s delay)
  empireLabelPositionDebounceRef: React.MutableRefObject<Record<string, NodeJS.Timeout>>

  // Show empire labels ref (synced from state)
  showEmpireLabelsRef: React.MutableRefObject<boolean>

  // Show ancient cities ref (synced from state)
  showAncientCitiesRef: React.MutableRefObject<boolean>

  // latLngTo3D conversion function
  latLngTo3D: (lat: number, lng: number, r: number) => THREE.Vector3

  // State values needed by some functions (passed as current values, not refs)
  showEmpireLabels: boolean
  showAncientCities: boolean
  empireYearOptions: Record<string, number[]>

  // Callback prop from Globe.tsx for notifying parent about loaded polygon data
  onEmpirePolygonsLoaded?: (empireId: string, year: number, features: any[]) => void

  // State setters needed by loadEmpireBorders
  setLoadingEmpires: (updater: (prev: Set<string>) => Set<string>) => void
  setEmpireYearOptions: (updater: (prev: Record<string, number[]>) => Record<string, number[]>) => void
  setEmpireCentroids: (updater: (prev: Record<string, Record<string, [number, number]>>) => Record<string, Record<string, [number, number]>>) => void
  setEmpireDefaultYears: (updater: (prev: Record<string, number>) => Record<string, number>) => void
  setEmpireYears: (updater: (prev: Record<string, number>) => Record<string, number>) => void
  setLoadedEmpires: (updater: (prev: Set<string>) => Set<string>) => void
  loadedEmpires: Set<string>
}


// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * getPolygonFillPositions - Creates fan triangulation from centroid for stencil-based polygon fill.
 * Processes outer ring + holes; stencil XOR handles inside/outside correctly.
 */
export function getPolygonFillPositions(
  coordinates: number[][][],
  radius: number,
  latLngTo3D: (lat: number, lng: number, r: number) => THREE.Vector3
): number[] {
  try {
    const outerRing = coordinates[0]
    if (!outerRing || outerRing.length < 3) return []

    // Calculate centroid of outer ring
    let centLng = 0, centLat = 0, count = 0
    for (const coord of outerRing) {
      if (Array.isArray(coord) && coord.length >= 2) {
        centLng += coord[0]
        centLat += coord[1]
        count++
      }
    }
    if (count === 0) return []
    centLng /= count
    centLat /= count

    const positions: number[] = []
    const centroid3D = latLngTo3D(centLat, centLng, radius)

    // Process all rings (outer + holes) with fan triangulation from centroid
    // The stencil buffer with XOR will correctly handle inside/outside
    const processRing = (ring: number[][]) => {
      const ringPoints: THREE.Vector3[] = []
      for (const coord of ring) {
        if (Array.isArray(coord) && coord.length >= 2) {
          ringPoints.push(latLngTo3D(coord[1], coord[0], radius))
        }
      }
      if (ringPoints.length < 3) return

      // Create fan triangles from centroid to each edge
      for (let i = 0; i < ringPoints.length; i++) {
        const p1 = ringPoints[i]
        const p2 = ringPoints[(i + 1) % ringPoints.length]

        // Triangle: centroid -> p1 -> p2
        positions.push(centroid3D.x, centroid3D.y, centroid3D.z)
        positions.push(p1.x, p1.y, p1.z)
        positions.push(p2.x, p2.y, p2.z)
      }
    }

    // Process outer ring
    processRing(outerRing)

    // Process holes (they will "subtract" via stencil XOR)
    for (let h = 1; h < coordinates.length; h++) {
      const hole = coordinates[h]
      if (Array.isArray(hole) && hole.length >= 3) {
        processRing(hole)
      }
    }

    return positions
  } catch (error) {
    console.warn('Error creating polygon fill:', error)
    return []
  }
}


// =============================================================================
// EMPIRE BORDER FUNCTIONS
// =============================================================================

/**
 * loadEmpireBorders - Load empire metadata and default year borders.
 * Fetches metadata.json, then loads default year boundaries, cities, and region labels.
 */
export async function loadEmpireBorders(
  empireId: string,
  ctx: GlobeRenderContext
): Promise<void> {
  if (!ctx.sceneRef.current) return
  const empire = EMPIRES.find(e => e.id === empireId)
  if (!empire || ctx.loadedEmpires.has(empireId)) return

  ctx.setLoadingEmpires(prev => new Set(prev).add(empireId))

  try {
    // First load metadata to get available years
    const metadataUrl = `/data/historical/${empire.file}/metadata.json`
    const metadataResponse = await offlineFetch(metadataUrl)
    if (!metadataResponse.ok) {
      console.warn(`Empire metadata not found for ${empire.name}`)
      return
    }
    const metadata = await metadataResponse.json()

    // Store year options, centroids, and default year
    const years = metadata.years as number[]
    ctx.setEmpireYearOptions(prev => ({ ...prev, [empireId]: years }))
    ctx.setEmpireCentroids(prev => ({ ...prev, [empireId]: metadata.centroids }))
    const defaultYear = metadata.defaultYear
    ctx.setEmpireDefaultYears(prev => ({ ...prev, [empireId]: defaultYear }))
    ctx.setEmpireYears(prev => ({ ...prev, [empireId]: defaultYear }))

    // Load the default year's boundaries (pass years directly since state hasn't updated yet)
    await loadEmpireBordersForYear(empireId, defaultYear, empire.color, true, ctx, years)

    // Load ancient cities for default year
    loadAncientCities(empireId, defaultYear, ctx)

    // Load region labels for default year
    loadRegionLabels(empireId, defaultYear, ctx)

    ctx.setLoadedEmpires(prev => new Set(prev).add(empireId))

  } catch (error) {
    console.warn(`Failed to load ${empire?.name}:`, error)
  } finally {
    ctx.setLoadingEmpires(prev => {
      const next = new Set(prev)
      next.delete(empireId)
      return next
    })
  }
}

/**
 * removeEmpireFromGlobe - Remove ALL objects tagged with empireId from globe.
 * No cache, just scan and remove. Disposes geometry and materials.
 */
export function removeEmpireFromGlobe(
  empireId: string,
  ctx: GlobeRenderContext
): void {
  const globe = ctx.sceneRef.current?.globe
  if (!globe) return

  // Scan globe children and collect all objects tagged with this empireId
  const toRemove: THREE.Object3D[] = []
  globe.children.forEach(child => {
    if (child.userData?.empireId === empireId) {
      toRemove.push(child)
    }
  })

  // Remove and dispose each one
  toRemove.forEach(obj => {
    globe.remove(obj)
    if (obj instanceof THREE.Mesh || obj instanceof THREE.Line) {
      obj.geometry.dispose()
      if (obj.material instanceof THREE.Material) {
        obj.material.dispose()
      }
    }
  })
}

/**
 * loadEmpireBordersForYear - Load empire borders for a specific year.
 * Fetches new data, removes old geometry AFTER new data is ready (prevents flickering),
 * then creates stencil-based fill and border lines.
 */
export async function loadEmpireBordersForYear(
  empireId: string,
  year: number,
  color: number,
  createLabel: boolean = false,
  ctx: GlobeRenderContext,
  yearOptions?: number[]  // Pass year options for initial label creation (before state updates)
): Promise<void> {
  if (!ctx.sceneRef.current) return

  const empire = EMPIRES.find(e => e.id === empireId)
  if (!empire) return

  // STEP 1: Fetch the new year's data FIRST (before removing old)
  try {
    const response = await offlineFetch(`/data/historical/${empire.file}/${year}.geojson`)
    if (!response.ok) return
    const data = await response.json()

    // Notify parent about loaded polygon data for "Within empires" filtering
    if (ctx.onEmpirePolygonsLoaded && data.features) {
      ctx.onEmpirePolygonsLoaded(empireId, year, data.features)
    }

    // Sync empire years to parent AFTER polygon data loads (prevents flash of all dots)
    ctx.onEmpireYearsChangeRef.current?.({ ...ctx.empireYearsRef.current, [empireId]: year })

    // Store polygon features for spatial label filtering
    ctx.empirePolygonFeaturesRef.current[empireId] = data.features.map((f: any) => ({
      geometry: f.geometry
    }))

    const { globe } = ctx.sceneRef.current
    // Front material for borders (visible on front side)
    const material = createFrontMaterial(color, 0.9)
    // Back material for borders at 10% opacity (same as coastlines)
    const backMaterial = createBackMaterial(color, 0.9)
    const stencilMaterial_ = createStencilMaterial()
    const fillMaterial = createEmpireFillMaterial(color, 0.15)

    if (ctx.sceneRef.current) {
      material.uniforms.uCameraPos.value.copy(ctx.sceneRef.current.camera.position)
      backMaterial.uniforms.uCameraPos.value.copy(ctx.sceneRef.current.camera.position)
      stencilMaterial_.uniforms.uCameraPos.value.copy(ctx.sceneRef.current.camera.position)
      fillMaterial.uniforms.uCameraPos.value.copy(ctx.sceneRef.current.camera.position)
    }

    // Register materials for camera position updates in animation loop
    ctx.shaderMaterialsRef.current.push(material)
    ctx.shaderMaterialsRef.current.push(backMaterial)
    ctx.shaderMaterialsRef.current.push(stencilMaterial_)
    ctx.shaderMaterialsRef.current.push(fillMaterial)

    const lines: THREE.Line[] = []
    const radius = LAYER_CONFIG.countryBorders.radius
    const fillRadius = 1.002

    // STEP 2: Collect ALL fill positions from ALL features into ONE merged array
    const allFillPositions: number[] = []

    data.features.forEach((feature: any) => {
      const geomType = feature.geometry?.type
      if (!geomType) return

      // Collect fill positions (merge all polygon parts)
      if (geomType === 'Polygon') {
        const positions = getPolygonFillPositions(feature.geometry.coordinates, fillRadius, ctx.latLngTo3D)
        allFillPositions.push(...positions)
      } else if (geomType === 'MultiPolygon') {
        feature.geometry.coordinates.forEach((polygon: number[][][]) => {
          const positions = getPolygonFillPositions(polygon, fillRadius, ctx.latLngTo3D)
          allFillPositions.push(...positions)
        })
      }
    })

    // STEP 3: Remove old geometry AFTER new data is ready (prevents flickering)
    removeEmpireFromGlobe(empireId, ctx)

    // STEP 4: Create stencil-based fill using two-pass rendering
    if (allFillPositions.length > 0) {
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(allFillPositions, 3))
      geometry.computeVertexNormals()

      // Pass 1: Stencil write mesh - renders fan triangles to stencil buffer only
      // Uses INVERT operation so odd-numbered overlaps are "inside" (even-odd fill rule)
      const stencilMesh = new THREE.Mesh(geometry, stencilMaterial_)
      stencilMesh.userData.empireId = empireId
      stencilMesh.renderOrder = 7  // Render first to set up stencil
      globe.add(stencilMesh)

      // Pass 2: Color fill mesh - tests stencil and draws color
      // Uses the same geometry - only pixels where stencil != 0 will be drawn
      const fillMesh = new THREE.Mesh(geometry, fillMaterial)
      fillMesh.userData.empireId = empireId
      fillMesh.renderOrder = 8  // Render after stencil
      globe.add(fillMesh)
    }

    // STEP 5: Create border lines (separate loop for clarity)
    data.features.forEach((feature: any) => {
      const geomType = feature.geometry?.type
      if (!geomType) return

      // Create border lines
      let coordSets: number[][][] = []
      if (geomType === 'LineString') {
        coordSets = [feature.geometry.coordinates]
      } else if (geomType === 'MultiLineString' || geomType === 'Polygon') {
        coordSets = feature.geometry.coordinates
      } else if (geomType === 'MultiPolygon') {
        coordSets = feature.geometry.coordinates.flat()
      }

      coordSets.forEach((coords: number[][]) => {
        if (!Array.isArray(coords) || coords.length < 2) return
        const points = coords.map((c: number[]) => ctx.latLngTo3D(c[1], c[0], radius))

        // Front-facing border line
        const line = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(points),
          material
        )
        line.userData.empireId = empireId
        line.renderOrder = 10
        globe.add(line)
        lines.push(line)

        // Back-facing border line (10% opacity like coastlines)
        // renderOrder < 0 ensures it's hidden in satellite mode (see satellite toggle effect)
        const backLine = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(points),
          backMaterial
        )
        backLine.userData.empireId = empireId
        backLine.renderOrder = -5  // Negative = hidden in satellite mode
        backLine.visible = !ctx.satelliteModeRef.current  // Hide immediately if satellite mode active
        globe.add(backLine)
      })
    })

    ctx.empireBorderLinesRef.current[empireId] = lines

    // Create label (pass yearOptions for initial load before state updates)
    if (createLabel && data.properties?.centroid) {
      const [lat, lng] = data.properties.centroid
      createEmpireLabel(empireId, empire.name, lat, lng, empire.startYear, empire.endYear, year, ctx, yearOptions)
      // Re-run collision detection to block geo labels near empire labels
      setTimeout(() => ctx.updateGeoLabelsRef.current?.(), 0)
    }

  } catch (error) {
    console.warn(`Failed to load ${empire?.name} year ${year}:`, error)
  }
}

/**
 * createEmpireLabel - Create empire name label at centroid with period text.
 * Creates a canvas-based texture with two lines (name + period), positioned on globe surface.
 */
export function createEmpireLabel(
  empireId: string,
  name: string,
  lat: number,
  lng: number,
  startYear: number | undefined,
  endYear: number | undefined,
  currentYear: number | undefined,
  ctx: GlobeRenderContext,
  yearOptions?: number[]
): void {
  if (!ctx.sceneRef.current) return

  // Remove existing label if any
  if (ctx.empireLabelsRef.current[empireId]) {
    ctx.sceneRef.current.scene.remove(ctx.empireLabelsRef.current[empireId])
  }

  // Create canvas for text (two lines: name, current period)
  const canvas = document.createElement('canvas')
  const canvasCtx = canvas.getContext('2d')
  if (!canvasCtx) return

  const fontSize = 57  // 10% bigger
  const periodFontSize = 40  // 40% bigger

  // Use passed yearOptions or fallback to state
  const years = yearOptions || ctx.empireYearOptions[empireId]

  // Calculate period text: (full range) showing current period
  let periodText = ''
  const fullRange = (startYear !== undefined && endYear !== undefined)
    ? `(${formatYear(startYear)} - ${formatYear(endYear)})`
    : ''
  if (currentYear !== undefined && years) {
    const currentIndex = years.indexOf(currentYear)
    const nextYear = currentIndex < years.length - 1 ? years[currentIndex + 1] : null
    const currentPeriod = formatYearPeriod(currentYear, nextYear)
    periodText = fullRange ? `${fullRange} showing ${currentPeriod}` : `showing ${currentPeriod}`
  } else if (currentYear !== undefined) {
    periodText = fullRange ? `${fullRange} showing ${formatYear(currentYear)}` : `showing ${formatYear(currentYear)}`
  } else {
    periodText = fullRange
  }

  // Measure text widths using same font as drawLabelWithShadow
  canvasCtx.font = `italic 600 ${fontSize}px ${ATLAS_FONT_FAMILY}`
  canvasCtx.letterSpacing = '8px'  // Account for letter spacing in measurement
  const nameMetrics = canvasCtx.measureText(name.toUpperCase())
  canvasCtx.letterSpacing = '0px'
  canvasCtx.font = `italic 400 ${periodFontSize}px ${ATLAS_FONT_FAMILY}`
  const periodMetrics = canvasCtx.measureText(periodText)

  const padding = fontSize * 0.6
  const textWidth = Math.max(nameMetrics.width, periodMetrics.width) + padding * 2
  const textHeight = (periodText ? fontSize * 2.0 : fontSize * 1.5) + padding

  canvas.width = textWidth
  canvas.height = textHeight

  const centerX = textWidth / 2
  const nameY = periodText ? textHeight * 0.35 : textHeight / 2
  const periodY = textHeight * 0.72

  canvasCtx.textAlign = 'center'
  canvasCtx.textBaseline = 'middle'

  // Draw empire name with letter spacing (orange-brown color)
  canvasCtx.letterSpacing = '8px'
  drawLabelWithShadow(canvasCtx, name.toUpperCase(), centerX, nameY, fontSize, '#DAA520', { bold: true, italic: true })  // Goldenrod
  canvasCtx.letterSpacing = '0px'

  // Draw current period (line 2) if available
  if (periodText) {
    drawLabelWithShadow(canvasCtx, periodText, centerX, periodY, periodFontSize, '#BDB76B', { italic: true })  // Dark khaki
  }

  // Create globe-tangent mesh
  const texture = new THREE.CanvasTexture(canvas)
  texture.needsUpdate = true

  // Position on globe surface - empire labels highest (5% above)
  const position = ctx.latLngTo3D(lat, lng, 1.05)

  // Base scale for screen-size calculation - empire labels are large
  const baseScale = 0.06
  const aspect = textWidth / textHeight

  // Create globe-tangent mesh (rotates with globe, faces outward)
  const mesh = createGlobeTangentLabel(texture, position, baseScale, aspect, 1400)  // Higher than geo labels (1000)

  // Start with opacity 0 to prevent flash, then fade in
  const material = mesh.material as THREE.ShaderMaterial
  if (material.uniforms?.opacity) {
    material.uniforms.opacity.value = 0
  }

  ctx.sceneRef.current.scene.add(mesh)
  ctx.empireLabelsRef.current[empireId] = mesh
  ctx.allLabelMeshesRef.current.push(mesh)

  // Initialize visibility state and fade in if toggle is on
  const key = `empire-label-${empireId}`
  ctx.labelVisibilityStateRef.current.set(key, false)  // Start hidden in state
  mesh.visible = false  // Start hidden
  if (ctx.showEmpireLabels) {
    ctx.labelVisibilityStateRef.current.set(key, true)
    fadeLabelIn(mesh, ctx.fadeManagerRef.current, key)
  }
}

/**
 * updateEmpireLabelText - Update empire label text only (without changing position).
 * Used during slider interaction to update the period text without recreating the label.
 */
export function updateEmpireLabelText(
  empireId: string,
  name: string,
  startYear: number | undefined,
  endYear: number | undefined,
  currentYear: number | undefined,
  ctx: GlobeRenderContext,
  yearOptionsParam?: number[]
): void {
  const existingMesh = ctx.empireLabelsRef.current[empireId]
  if (!existingMesh) return

  // Create canvas for text (two lines: name, current period)
  const canvas = document.createElement('canvas')
  const canvasCtx = canvas.getContext('2d')
  if (!canvasCtx) return

  const fontSize = 57  // 10% bigger
  const periodFontSize = 40  // 40% bigger

  // Calculate period text: (full range) current period
  let periodText = ''
  const fullRange = (startYear !== undefined && endYear !== undefined)
    ? `(${formatYear(startYear)} - ${formatYear(endYear)})`
    : ''
  if (currentYear !== undefined) {
    // Use passed yearOptions or fall back to state
    const yearOpts = yearOptionsParam || ctx.empireYearOptions[empireId]
    let currentPeriod = ''
    if (yearOpts) {
      const currentIndex = yearOpts.indexOf(currentYear)
      const nextYear = currentIndex < yearOpts.length - 1 ? yearOpts[currentIndex + 1] : null
      currentPeriod = formatYearPeriod(currentYear, nextYear)
    } else {
      currentPeriod = formatYear(currentYear)
    }
    periodText = fullRange ? `${fullRange} showing ${currentPeriod}` : `showing ${currentPeriod}`
  } else {
    periodText = fullRange
  }

  // Measure text widths using same font as drawLabelWithShadow
  canvasCtx.font = `italic 600 ${fontSize}px ${ATLAS_FONT_FAMILY}`
  canvasCtx.letterSpacing = '8px'  // Account for letter spacing in measurement
  const nameMetrics = canvasCtx.measureText(name.toUpperCase())
  canvasCtx.letterSpacing = '0px'
  canvasCtx.font = `italic 400 ${periodFontSize}px ${ATLAS_FONT_FAMILY}`
  const periodMetrics = canvasCtx.measureText(periodText)

  const padding = fontSize * 0.6
  const textWidth = Math.max(nameMetrics.width, periodMetrics.width) + padding * 2
  const textHeight = (periodText ? fontSize * 2.0 : fontSize * 1.5) + padding

  canvas.width = textWidth
  canvas.height = textHeight

  const centerX = textWidth / 2
  const nameY = periodText ? textHeight * 0.35 : textHeight / 2
  const periodY = textHeight * 0.72

  canvasCtx.textAlign = 'center'
  canvasCtx.textBaseline = 'middle'

  // Draw empire name with letter spacing (orange-brown color)
  canvasCtx.letterSpacing = '8px'
  drawLabelWithShadow(canvasCtx, name.toUpperCase(), centerX, nameY, fontSize, '#DAA520', { bold: true, italic: true })  // Goldenrod
  canvasCtx.letterSpacing = '0px'

  // Draw current period (line 2) if available
  if (periodText) {
    drawLabelWithShadow(canvasCtx, periodText, centerX, periodY, periodFontSize, '#BDB76B', { italic: true })  // Dark khaki
  }

  // Update the existing mesh's texture
  const newTexture = new THREE.CanvasTexture(canvas)
  newTexture.needsUpdate = true

  // Dispose old texture and update material (ShaderMaterial uses uniforms.map)
  const material = existingMesh.material as THREE.ShaderMaterial
  if (material.uniforms?.map?.value) {
    material.uniforms.map.value.dispose()
  }
  if (material.uniforms?.map) {
    material.uniforms.map.value = newTexture
  }
  material.needsUpdate = true

  // Update aspect ratio for proper scaling (base scale stays the same)
  existingMesh.userData.aspect = textWidth / textHeight
}

/**
 * animateEmpireLabelPosition - Animate empire label position smoothly to new location.
 * Uses ease-out cubic for smooth deceleration.
 */
export function animateEmpireLabelPosition(
  empireId: string,
  targetLat: number,
  targetLng: number,
  ctx: GlobeRenderContext,
  duration: number = 500
): void {
  const mesh = ctx.empireLabelsRef.current[empireId]
  if (!mesh) return

  const targetPosition = ctx.latLngTo3D(targetLat, targetLng, 1.05)
  const startPosition = mesh.position.clone()
  const startTime = performance.now()

  const animate = (currentTime: number) => {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / duration, 1)

    // Ease out cubic for smooth deceleration
    const eased = 1 - Math.pow(1 - progress, 3)

    mesh.position.lerpVectors(startPosition, targetPosition, eased)
    // Update orientation to stay tangent to globe
    mesh.lookAt(mesh.position.clone().multiplyScalar(2))

    if (progress < 1) {
      requestAnimationFrame(animate)
    }
  }

  requestAnimationFrame(animate)
}

/**
 * createRegionLabel - Create region label mesh (smaller than empire label, globe-tangent).
 * Returns the mesh without adding it to the scene.
 */
export function createRegionLabel(
  regionName: string,
  lat: number,
  lng: number,
  ctx: GlobeRenderContext
): GlobeLabelMesh {
  const canvas = document.createElement('canvas')
  const canvasCtx = canvas.getContext('2d')!

  const fontSize = 32
  canvasCtx.font = `italic 400 ${fontSize}px ${ATLAS_FONT_FAMILY}`
  const metrics = canvasCtx.measureText(regionName)
  const textWidth = metrics.width + 20
  const textHeight = fontSize * 1.5

  canvas.width = textWidth
  canvas.height = textHeight

  // Draw region name using unified shadow function
  canvasCtx.textAlign = 'center'
  canvasCtx.textBaseline = 'middle'

  const centerX = textWidth / 2
  const centerY = textHeight / 2

  drawLabelWithShadow(canvasCtx, regionName, centerX, centerY, fontSize, '#DEB887', { italic: true })  // Burlywood - bright tan

  const texture = new THREE.CanvasTexture(canvas)
  texture.needsUpdate = true

  // Position on globe surface - region labels below empire (3% above)
  const position = ctx.latLngTo3D(lat, lng, 1.03)

  // Base scale for screen-size calculation - region labels medium size
  const baseScale = 0.02
  const aspect = textWidth / textHeight

  // Create globe-tangent mesh (rotates with globe, faces outward)
  const mesh = createGlobeTangentLabel(texture, position, baseScale, aspect, 998)  // Just below empire labels

  // Start with opacity 0 for fade-in
  const material = mesh.material as THREE.ShaderMaterial
  if (material.uniforms?.opacity) {
    material.uniforms.opacity.value = 0
  }

  return mesh
}

/**
 * loadRegionLabels - Load and display region labels for an empire.
 * Fetches regions.json if not cached, filters regions active in the given year
 * and spatially inside the current empire polygon.
 */
export async function loadRegionLabels(
  empireId: string,
  year: number,
  ctx: GlobeRenderContext
): Promise<void> {
  if (!ctx.sceneRef.current) return

  // Load region data if not cached
  if (!ctx.regionDataRef.current) {
    try {
      const response = await offlineFetch('/data/historical/regions.json')
      if (response.ok) {
        ctx.regionDataRef.current = await response.json()
      }
    } catch (error) {
      console.warn('Failed to load region data:', error)
      return
    }
  }

  const regions = ctx.regionDataRef.current?.[empireId]
  if (!regions) return

  // Remove existing region labels for this empire
  if (ctx.regionLabelsRef.current[empireId]) {
    ctx.regionLabelsRef.current[empireId].forEach(mesh => {
      ctx.sceneRef.current?.scene.remove(mesh)
      // Remove from tracking ref
      const idx = ctx.allLabelMeshesRef.current.indexOf(mesh)
      if (idx !== -1) ctx.allLabelMeshesRef.current.splice(idx, 1)
    })
  }

  // Filter regions active in this year
  let activeRegions = regions.filter(region => {
    const [startYear, endYear] = region.years
    return year >= startYear && year <= endYear
  })

  // Filter regions that are spatially inside the current empire polygon
  const polygonFeatures = ctx.empirePolygonFeaturesRef.current[empireId]
  if (polygonFeatures && polygonFeatures.length > 0) {
    activeRegions = activeRegions.filter(region => {
      const coords: [number, number] = [region.lng, region.lat]
      // Check if region center is inside any polygon feature
      for (const feature of polygonFeatures) {
        if (feature.geometry && pointInGeoJSONGeometry(coords, feature.geometry)) {
          return true
        }
      }
      return false
    })
  }

  // Create new region labels
  const meshes: GlobeLabelMesh[] = []
  activeRegions.forEach((region, idx) => {
    const mesh = createRegionLabel(region.name, region.lat, region.lng, ctx)
    mesh.visible = false  // Start hidden
    ctx.sceneRef.current?.scene.add(mesh)
    meshes.push(mesh)
    ctx.allLabelMeshesRef.current.push(mesh)

    // Initialize visibility state and fade in if toggle is on
    const key = `region-${empireId}-${idx}`
    ctx.labelVisibilityStateRef.current.set(key, false)
    if (ctx.showEmpireLabels) {
      ctx.labelVisibilityStateRef.current.set(key, true)
      fadeLabelIn(mesh, ctx.fadeManagerRef.current, key)
    }
  })

  ctx.regionLabelsRef.current[empireId] = meshes
}

/**
 * removeRegionLabels - Remove region labels for an empire.
 * Removes meshes from scene and tracking refs.
 */
export function removeRegionLabels(
  empireId: string,
  ctx: GlobeRenderContext
): void {
  if (!ctx.sceneRef.current) return
  const meshes = ctx.regionLabelsRef.current[empireId]
  if (meshes) {
    meshes.forEach(mesh => {
      ctx.sceneRef.current?.scene.remove(mesh)
      // Remove from tracking ref
      const idx = ctx.allLabelMeshesRef.current.indexOf(mesh)
      if (idx !== -1) ctx.allLabelMeshesRef.current.splice(idx, 1)
    })
    delete ctx.regionLabelsRef.current[empireId]
  }
}

/**
 * createCityMarker - Create city marker mesh (globe-tangent).
 * Returns the mesh without adding it to the scene.
 */
export function createCityMarker(
  cityName: string,
  lat: number,
  lng: number,
  type: 'capital' | 'major',
  ctx: GlobeRenderContext
): GlobeLabelMesh {
  const canvas = document.createElement('canvas')
  const canvasCtx = canvas.getContext('2d')!

  const fontSize = type === 'capital' ? 21 : 22
  const padding = 10

  canvasCtx.font = `400 ${fontSize}px ${ATLAS_FONT_FAMILY}`
  const metrics = canvasCtx.measureText(cityName)
  const textWidth = metrics.width + padding * 2
  const textHeight = fontSize * 1.5

  canvas.width = textWidth
  canvas.height = textHeight

  // Draw city name using unified shadow function (no dot)
  canvasCtx.textAlign = 'center'
  canvasCtx.textBaseline = 'middle'

  const textX = textWidth / 2
  const textY = textHeight / 2
  const textColor = type === 'capital' ? '#F0E68C' : '#DEB887'  // Capitals: khaki/gold, Major cities: burlywood

  drawLabelWithShadow(canvasCtx, cityName, textX, textY, fontSize, textColor)

  const texture = new THREE.CanvasTexture(canvas)
  texture.needsUpdate = true

  // Position on globe surface - cities below regions (1.2% above for capitals, 1% for major)
  const position = ctx.latLngTo3D(lat, lng, type === 'capital' ? 1.012 : 1.01)

  // Base scale for screen-size calculation - city markers small
  const baseScale = type === 'capital' ? 0.027 : 0.028
  const aspect = textWidth / textHeight

  // Create globe-tangent mesh (rotates with globe, faces outward)
  const mesh = createGlobeTangentLabel(texture, position, baseScale, aspect, 999)  // Just below empire labels

  // Start with opacity 0 for fade-in
  const material = mesh.material as THREE.ShaderMaterial
  if (material.uniforms?.opacity) {
    material.uniforms.opacity.value = 0
  }

  return mesh
}

/**
 * loadAncientCities - Load and display ancient cities for an empire.
 * Robust with cancellation support via AbortController.
 * Fetches capitals.json if not cached, filters cities active in the given year
 * and spatially inside the current empire polygon.
 */
export async function loadAncientCities(
  empireId: string,
  year: number,
  ctx: GlobeRenderContext
): Promise<void> {
  if (!ctx.sceneRef.current || !ctx.showAncientCities) return

  // Cancel any pending load for this empire
  if (ctx.empireLoadAbortRef.current[empireId]) {
    ctx.empireLoadAbortRef.current[empireId].abort()
  }

  // Create new AbortController for this load
  const abortController = new AbortController()
  ctx.empireLoadAbortRef.current[empireId] = abortController
  const signal = abortController.signal

  // Helper to check if we should continue
  const shouldContinue = () => {
    if (signal.aborted) return false
    if (!ctx.visibleEmpiresRef.current.has(empireId)) return false
    if (!ctx.sceneRef.current) return false
    return true
  }

  // Remove existing city markers for this empire (synchronous, always safe)
  if (ctx.ancientCitiesRef.current[empireId]) {
    ctx.ancientCitiesRef.current[empireId].forEach(mesh => {
      ctx.sceneRef.current?.scene.remove(mesh)
      const idx = ctx.allLabelMeshesRef.current.indexOf(mesh)
      if (idx !== -1) ctx.allLabelMeshesRef.current.splice(idx, 1)
    })
    delete ctx.ancientCitiesRef.current[empireId]
  }

  // Early exit if cancelled
  if (!shouldContinue()) return

  // Load cities data if not cached
  if (!ctx.ancientCitiesDataRef.current[empireId]) {
    try {
      const response = await offlineFetch('/data/historical/capitals.json', { signal })
      if (!shouldContinue()) return
      const allCities = await response.json()
      if (!shouldContinue()) return
      // Cache all cities data
      Object.keys(allCities).forEach(id => {
        ctx.ancientCitiesDataRef.current[id] = allCities[id]
      })
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return  // Cancelled, not an error
      console.warn('Failed to load ancient cities data:', error)
      return
    }
  }

  // Final check before creating markers
  if (!shouldContinue()) return

  const cities = ctx.ancientCitiesDataRef.current[empireId]
  if (!cities) return

  // Filter cities that existed in the current year
  let activeCities = cities.filter(city => {
    const [startYear, endYear] = city.years
    return year >= startYear && year <= endYear
  })

  // Filter cities that are spatially inside the current empire polygon
  const polygonFeatures = ctx.empirePolygonFeaturesRef.current[empireId]
  if (polygonFeatures && polygonFeatures.length > 0) {
    activeCities = activeCities.filter(city => {
      const coords: [number, number] = [city.lng, city.lat]
      // Check if city is inside any polygon feature
      for (const feature of polygonFeatures) {
        if (feature.geometry && pointInGeoJSONGeometry(coords, feature.geometry)) {
          return true
        }
      }
      return false
    })
  }

  // Create markers for active cities
  const markers: GlobeLabelMesh[] = []
  activeCities.forEach((city, idx) => {
    if (!shouldContinue()) return  // Check during loop too
    const marker = createCityMarker(
      city.name,
      city.lat,
      city.lng,
      city.type as 'capital' | 'major',
      ctx
    )
    marker.visible = false  // Start hidden
    ctx.sceneRef.current?.scene.add(marker)
    markers.push(marker)
    ctx.allLabelMeshesRef.current.push(marker)

    // Initialize visibility state and fade in
    const key = `city-${empireId}-${idx}`
    ctx.labelVisibilityStateRef.current.set(key, true)
    fadeLabelIn(marker, ctx.fadeManagerRef.current, key)
  })

  // Only store if we completed successfully and empire is still visible
  if (shouldContinue() && markers.length > 0) {
    ctx.ancientCitiesRef.current[empireId] = markers
  }

  // Clean up AbortController reference
  if (ctx.empireLoadAbortRef.current[empireId] === abortController) {
    delete ctx.empireLoadAbortRef.current[empireId]
  }
}

/**
 * removeAncientCities - Remove ancient cities for an empire.
 * Aborts pending loads, removes existing markers from scene, idempotent.
 */
export function removeAncientCities(
  empireId: string,
  ctx: GlobeRenderContext
): void {
  // Abort any pending load for this empire first
  if (ctx.empireLoadAbortRef.current[empireId]) {
    ctx.empireLoadAbortRef.current[empireId].abort()
    delete ctx.empireLoadAbortRef.current[empireId]
  }

  // Remove existing markers from scene
  if (ctx.ancientCitiesRef.current[empireId]) {
    ctx.ancientCitiesRef.current[empireId].forEach(mesh => {
      ctx.sceneRef.current?.scene.remove(mesh)
      const idx = ctx.allLabelMeshesRef.current.indexOf(mesh)
      if (idx !== -1) ctx.allLabelMeshesRef.current.splice(idx, 1)
    })
    delete ctx.ancientCitiesRef.current[empireId]
  }
}
