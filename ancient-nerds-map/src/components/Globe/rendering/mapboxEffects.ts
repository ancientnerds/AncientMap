// =============================================================================
// MAPBOX EFFECTS - Extracted from Globe.tsx
// Contains all Mapbox GL JS synchronization effects for the Globe component.
// =============================================================================

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { SiteData, SOURCE_COLORS, getCategoryColor } from '../../../data/sites'
import { FilterMode } from '../../../App'
import { getThreeJsView, viewToMapbox, latLngToCartesian } from '../../../utils/geoMath'
import { MapboxGlobeService, type MapboxMarkerData } from '../../../services/MapboxGlobeService'
import { CAMERA } from '../../../config/globeConstants'

// =============================================================================
// SHARED INTERFACES
// =============================================================================

/**
 * Scene refs used by Mapbox effects - mirrors the sceneRef.current shape in Globe.tsx
 */
export interface SceneRefs {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  controls: OrbitControls
  points: THREE.Points | null
  backPoints: THREE.Points | null
  shadowPoints: THREE.Points | null
  globe: THREE.Mesh
}

/**
 * All refs and state setters needed by the Mapbox initialization effect.
 */
export interface MapboxInitEffectDeps {
  mapboxContainerRef: React.RefObject<HTMLDivElement | null>
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
}

/**
 * All refs and state setters needed by the texture-ready effect.
 */
export interface TextureReadyEffectDeps {
  texturesReady: boolean
  texturesReadyRef: React.MutableRefObject<boolean>
  basemapMeshRef: React.MutableRefObject<THREE.Mesh | null>
  sceneRef: React.MutableRefObject<SceneRefs | null>
}

/**
 * All refs and state setters needed by the auto-switch effect.
 */
export interface AutoSwitchEffectDeps {
  zoom: number
  showMapbox: boolean
  setShowMapbox: (value: boolean) => void
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
  justEnteredMapbox: React.MutableRefObject<boolean>
  contextIsOffline: boolean
  hasMapboxTilesCached: boolean
  setShowMapboxOfflineWarning: (value: boolean) => void
}

/**
 * All refs and state setters needed by the main mode switching effect.
 */
export interface ModeSwitchEffectDeps {
  showMapbox: boolean
  onSiteClick: ((site: SiteData | null) => void) | undefined
  prevShowMapboxRef: React.MutableRefObject<boolean>
  showMapboxRef: React.MutableRefObject<boolean>
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
  sceneRef: React.MutableRefObject<SceneRefs | null>
  mapboxTransitioningRef: React.MutableRefObject<boolean>
  mapboxBaseZoomRef: React.MutableRefObject<number>
  justEnteredMapbox: React.MutableRefObject<boolean>
  zoomRef: React.MutableRefObject<number>
  isManualZoom: React.MutableRefObject<boolean>
  isWheelZoom: React.MutableRefObject<boolean>
  wheelCursorLatLng: React.MutableRefObject<{ lat: number; lng: number } | null>
  containerRef: React.RefObject<HTMLDivElement | null>
  measureModeRef: React.MutableRefObject<boolean | undefined>
  measureSnapEnabledRef: React.MutableRefObject<boolean | undefined>
  measurementsRef: React.MutableRefObject<Array<{ id: string; points: [[number, number], [number, number]]; snapped: [boolean, boolean]; color: string }>>
  currentMeasurePointsRef: React.MutableRefObject<Array<{ coords: [number, number]; snapped: boolean }>>
  sitesRef: React.MutableRefObject<SiteData[]>
  siteClickJustHappenedRef: React.MutableRefObject<boolean>
  onSiteSelectRef: React.MutableRefObject<((siteId: string | null, ctrlKey: boolean) => void) | undefined>
  onMeasurePointAddRef: React.MutableRefObject<((coords: [number, number], snapped: boolean) => void) | undefined>
  showTooltipsRef: React.MutableRefObject<boolean>
  isFrozenRef: React.MutableRefObject<boolean>
  frozenSiteRef: React.MutableRefObject<SiteData | null>
  currentHoveredSiteRef: React.MutableRefObject<SiteData | null>
  lastSeenSiteRef: React.MutableRefObject<SiteData | null>
  highlightFrozenRef: React.MutableRefObject<boolean>
  lastMousePosRef: React.MutableRefObject<{ x: number; y: number }>
  lastMoveTimeRef: React.MutableRefObject<number>
  isHoveringTooltipRef: React.MutableRefObject<boolean>
  lastCoordsUpdateRef: React.MutableRefObject<number>
  listHighlightedSitesRef: React.MutableRefObject<SiteData[]>
  listHighlightedPositionsRef: React.MutableRefObject<Map<string, { x: number; y: number }>>
  // State setters
  setHoveredSite: (site: SiteData | null) => void
  setFrozenSite: (site: SiteData | null) => void
  setIsFrozen: (frozen: boolean) => void
  setTooltipPos: (pos: { x: number; y: number }) => void
  setCursorCoords: (coords: { lat: number; lon: number } | null) => void
  setZoom: (updater: (currentZoom: number) => number) => void
  setListHighlightedSites: (sites: SiteData[]) => void
  setListHighlightedPositions: (positions: Map<string, { x: number; y: number }>) => void
  onProximitySet?: (coords: [number, number]) => void
}

/**
 * All refs and state needed by the Mapbox sites sync effect.
 */
export interface SitesSyncEffectDeps {
  showMapbox: boolean
  sites: (SiteData & { isInsideProximity?: boolean })[]
  filterMode: FilterMode
  sourceColors?: Record<string, string>
  countryColors?: Record<string, string>
  searchWithinProximity?: boolean
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
}

/**
 * All refs and state needed by the Mapbox measurements sync effect.
 */
export interface MeasurementsSyncEffectDeps {
  showMapbox: boolean
  measurements: Array<{ id: string; points: [[number, number], [number, number]]; snapped: [boolean, boolean]; color: string }>
  currentMeasurePoints: Array<{ coords: [number, number]; snapped: boolean }>
  measureUnit: 'km' | 'miles'
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
}

/**
 * All refs and state needed by the Mapbox proximity circles sync effect.
 */
export interface ProximityCircleSyncEffectDeps {
  showMapbox: boolean
  proximity?: { center: [number, number] | null; radius: number; isSettingOnGlobe: boolean }
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
}

/**
 * All refs and state needed by the Mapbox frozen/selected sites sync effect.
 */
export interface SelectedSitesSyncEffectDeps {
  showMapbox: boolean
  listFrozenSiteIds: string[]
  sitesRef: React.MutableRefObject<SiteData[]>
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
}

// =============================================================================
// TRANSITION POINT CONSTANT
// =============================================================================

/**
 * Auto-switch threshold: 0-65% = Three.js, 66-100% = Mapbox.
 * Single threshold at 66% - no hysteresis for smooth slider behavior.
 */
export const TRANSITION_POINT = 66

// =============================================================================
// EFFECT FUNCTIONS
// =============================================================================

/**
 * Creates the Mapbox GL JS initialization effect body.
 * Corresponds to Globe.tsx lines ~2881-2902.
 *
 * Usage in useEffect:
 *   useEffect(() => createMapboxInitEffect(deps), [])
 *
 * @returns Cleanup function that disposes the Mapbox service.
 */
export function createMapboxInitEffect(
  deps: MapboxInitEffectDeps
): (() => void) | undefined {
  if (!deps.mapboxContainerRef.current) return

  const mapboxService = new MapboxGlobeService()
  deps.mapboxServiceRef.current = mapboxService

  console.log('[Mapbox] Initializing Mapbox GL JS...')
  mapboxService.initialize(deps.mapboxContainerRef.current, 'dark')
    .then(() => {
      console.log('[Mapbox] Mapbox GL JS ready')
      // Initially hidden via CSS (opacity: 0) until showMapbox triggers mapbox-primary-mode class
    })
    .catch((err) => {
      console.error('[Mapbox] Failed to initialize:', err)
    })

  return () => {
    console.log('[Mapbox] Disposing Mapbox GL JS')
    mapboxService.dispose()
    deps.mapboxServiceRef.current = null
  }
}

/**
 * Creates the texture-ready effect body.
 * Forces basemap visible when textures become ready.
 * Corresponds to Globe.tsx lines ~7055-7071.
 *
 * Usage in useEffect:
 *   useEffect(() => createTextureReadyEffect(deps), [texturesReady])
 */
export function createTextureReadyEffect(
  deps: TextureReadyEffectDeps
): void {
  deps.texturesReadyRef.current = deps.texturesReady
  if (!deps.texturesReady) return

  const basemapMesh = deps.basemapMeshRef.current
  const globeBase = deps.sceneRef.current?.globe

  if (basemapMesh && !basemapMesh.visible) {
    basemapMesh.visible = true
  }

  // Hide globe base visual (set opacity to 0, NOT visible=false which hides children/vector layers)
  if (globeBase && basemapMesh?.visible) {
    const globeMaterial = globeBase.material as THREE.MeshBasicMaterial
    globeMaterial.opacity = 0
  }
}

/**
 * Creates the auto-switch effect body.
 * Auto-switches between Three.js and Mapbox based on zoom level.
 * Corresponds to Globe.tsx lines ~7078-7096.
 *
 * Usage in useEffect:
 *   useEffect(() => createAutoSwitchEffect(deps), [zoom, showMapbox, contextIsOffline, hasMapboxTilesCached])
 */
export function createAutoSwitchEffect(
  deps: AutoSwitchEffectDeps
): void {
  if (!deps.mapboxServiceRef.current?.getIsInitialized()) return

  if (deps.zoom >= TRANSITION_POINT && !deps.showMapbox) {
    console.log('[AUTO-SWITCH] Zoom >= 66%, switching to Mapbox')
    // Set flag BEFORE enabling Mapbox to prevent zoom effect from running
    deps.justEnteredMapbox.current = true
    deps.setShowMapbox(true)
    // Show warning if offline and satellite basemap not cached
    if (deps.contextIsOffline && !deps.hasMapboxTilesCached) {
      deps.setShowMapboxOfflineWarning(true)
    }
  } else if (deps.zoom < TRANSITION_POINT && deps.showMapbox) {
    console.log('[AUTO-SWITCH] Zoom < 66%, switching to Three.js')
    deps.setShowMapbox(false)
    // Hide warning when switching back to Three.js
    deps.setShowMapboxOfflineWarning(false)
  }
}

/**
 * Creates the main mode switching effect body.
 * Handles entering/exiting Mapbox primary mode with full event handler setup.
 * Corresponds to Globe.tsx lines ~7101-7444.
 *
 * Usage in useEffect:
 *   useEffect(() => createModeSwitchEffect(deps), [showMapbox, onSiteClick])
 */
export function createModeSwitchEffect(
  deps: ModeSwitchEffectDeps
): void {
  // Detect if mode actually changed (vs just onSiteClick dependency triggering re-run)
  const modeActuallyChanged = deps.prevShowMapboxRef.current !== deps.showMapbox
  deps.prevShowMapboxRef.current = deps.showMapbox
  deps.showMapboxRef.current = deps.showMapbox

  // Skip effect if mode didn't actually change (prevents zoom jump when clicking tooltips)
  if (!modeActuallyChanged) {
    return
  }

  const mapboxService = deps.mapboxServiceRef.current

  if (!deps.sceneRef.current || !mapboxService?.getIsInitialized()) {
    return
  }

  const { camera, controls, points, backPoints } = deps.sceneRef.current

  if (deps.showMapbox) {
    // === ENTERING MAPBOX MODE ===
    // justEnteredMapbox flag is already set by auto-switch effect

    // Clear Three.js tooltip state to prevent conflicts with Mapbox hover system
    deps.setHoveredSite(null)
    deps.setFrozenSite(null)
    deps.setIsFrozen(false)
    deps.isFrozenRef.current = false
    deps.currentHoveredSiteRef.current = null
    deps.lastSeenSiteRef.current = null
    deps.highlightFrozenRef.current = false

    // Use unified GlobeView for perfect sync - NO zoom adjustment
    const view = getThreeJsView(camera)
    const mapboxCamera = viewToMapbox(view)

    console.log('[SYNC] === ENTERING MAPBOX ===')
    console.log('[SYNC] GlobeView:', view)
    console.log('[SYNC] → Mapbox camera:', mapboxCamera)

    mapboxService.setCamera(mapboxCamera.lat, mapboxCamera.lng, mapboxCamera.zoom)

    // Store the base zoom percent for the Mapbox zoom effect to use
    // Must use same scale as MapboxGlobeService (0.7-18 range for full street-level zoom)
    const MAPBOX_FULL_ZOOM_MIN = 0.7
    const MAPBOX_FULL_ZOOM_MAX = 18
    deps.mapboxBaseZoomRef.current = ((mapboxCamera.zoom - MAPBOX_FULL_ZOOM_MIN) / (MAPBOX_FULL_ZOOM_MAX - MAPBOX_FULL_ZOOM_MIN)) * 100
    console.log('[SYNC] Base Mapbox zoom percent:', deps.mapboxBaseZoomRef.current)

    // Slider position is already correct since user dragged it to trigger mode switch
    // No need to update it here (would cause feedback loop)

    // Disable Three.js controls
    controls.enabled = false

    // Set up all callbacks BEFORE enabling primary mode (so they're ready when isInteractive becomes true)

    // Set up site click callback (skip if in measure/proximity mode)
    mapboxService.onSiteClick((siteId: string) => {
      // Mark that a site was clicked (prevents map click from deselecting)
      deps.siteClickJustHappenedRef.current = true
      setTimeout(() => { deps.siteClickJustHappenedRef.current = false }, 50)

      // Don't handle site clicks in measure/proximity mode (let mapClickCallback handle it)
      const isProximityMode = deps.containerRef.current?.dataset.proximityMode === 'true'
      if (isProximityMode || deps.measureModeRef.current) return

      const site = deps.sitesRef.current.find(s => s.id === siteId)
      if (site) {
        // Clear freeze state to prevent flicker when transitioning to selected label
        deps.isFrozenRef.current = false
        deps.setIsFrozen(false)
        deps.setFrozenSite(null)
        deps.setHoveredSite(null)
        deps.currentHoveredSiteRef.current = null
        deps.lastSeenSiteRef.current = null

        // SYNCHRONOUSLY set up the selected label position so it renders immediately
        // This prevents flicker when hover tooltip disappears before useEffect runs
        const [lng, lat] = site.coordinates
        const screenPos = deps.mapboxServiceRef.current?.projectToScreen(lng, lat)
        if (screenPos) {
          const newPositions = new Map(deps.listHighlightedPositionsRef.current)
          newPositions.set(site.id, screenPos)
          deps.listHighlightedPositionsRef.current = newPositions
          deps.setListHighlightedPositions(newPositions)

          // Also add to highlighted sites list
          if (!deps.listHighlightedSitesRef.current.find(s => s.id === site.id)) {
            const newSites = [...deps.listHighlightedSitesRef.current, site]
            deps.listHighlightedSitesRef.current = newSites
            deps.setListHighlightedSites(newSites)
          }
        }

        // Select site (shows green ring) - same as 3D globe click
        // Note: Mapbox doesn't have keyboard events, so no ctrlKey support
        if (deps.onSiteSelectRef.current) {
          deps.onSiteSelectRef.current(siteId, false)
        }
      }
    })

    // Set up site hover callback - feeds into same tooltip system as Three.js
    mapboxService.onSiteHover((siteId: string | null, x: number, y: number) => {
      // Update mouse tracking refs for freeze logic (same as Three.js mousemove)
      // Don't update position while hovering over tooltip (keeps the -1000 trick working)
      if (!deps.isHoveringTooltipRef.current) {
        const lastPos = deps.lastMousePosRef.current
        if (lastPos.x !== x || lastPos.y !== y) {
          deps.lastMousePosRef.current = { x, y }
          deps.lastMoveTimeRef.current = Date.now()
        }
      }

      if (siteId && deps.showTooltipsRef.current) {
        // Use sitesRef to avoid stale closure
        const site = deps.sitesRef.current.find(s => s.id === siteId)
        if (site) {
          // Feed into same state as Three.js tooltips
          deps.setHoveredSite(site)
          // Only update position if NOT frozen - frozen label stays at freeze position
          if (!deps.isFrozenRef.current) {
            deps.setTooltipPos({ x, y })
          }
          // Update refs for freeze logic
          deps.currentHoveredSiteRef.current = site
        }
      } else {
        // Clear tooltip when not hovering over a site
        // UNLESS: frozen OR hovering over the tooltip itself
        if (!deps.isFrozenRef.current && !deps.isHoveringTooltipRef.current) {
          deps.setHoveredSite(null)
          deps.currentHoveredSiteRef.current = null
        }
      }
    })

    // Set up global mouse move callback - tracks cursor movement for freeze timing and coordinates
    mapboxService.onMouseMove((x: number, y: number) => {
      // Update cursor coordinates (throttled)
      const now = Date.now()
      if (now - deps.lastCoordsUpdateRef.current > 50) {
        const coords = mapboxService.unprojectToLatLng(x, y)
        if (coords) {
          deps.setCursorCoords({ lat: coords.lat, lon: coords.lng })
        } else {
          deps.setCursorCoords(null)
        }
        deps.lastCoordsUpdateRef.current = now
      }

      // Don't update position while hovering over tooltip (keeps the -1000 trick working)
      if (deps.isHoveringTooltipRef.current) return

      const lastPos = deps.lastMousePosRef.current
      if (lastPos.x !== x || lastPos.y !== y) {
        deps.lastMousePosRef.current = { x, y }
        deps.lastMoveTimeRef.current = Date.now()
      }
    })

    // Set up mouse leave callback - clear coordinates when mouse leaves map
    mapboxService.onMouseLeave(() => {
      deps.setCursorCoords(null)
    })

    // Set up camera move callback - updates frozen tooltip position during pan/rotate/zoom
    // This ensures the tooltip stays attached to the site dot during camera movement
    mapboxService.onCameraMove(() => {
      // Update frozen/selected site tooltip position
      if (deps.isFrozenRef.current && deps.frozenSiteRef.current) {
        const site = deps.frozenSiteRef.current
        const [lng, lat] = site.coordinates
        const screenPos = deps.mapboxServiceRef.current?.projectToScreen(lng, lat)
        if (screenPos) {
          deps.setTooltipPos({ x: screenPos.x, y: screenPos.y })
        }
      }

      // Update list-highlighted site positions (selected labels that follow the site)
      if (deps.listHighlightedSitesRef.current.length > 0) {
        const newPositions = new Map<string, { x: number, y: number }>()
        for (const site of deps.listHighlightedSitesRef.current) {
          const [lng, lat] = site.coordinates
          const screenPos = deps.mapboxServiceRef.current?.projectToScreen(lng, lat)
          if (screenPos) {
            newPositions.set(site.id, screenPos)
          }
        }
        deps.listHighlightedPositionsRef.current = newPositions
        deps.setListHighlightedPositions(newPositions)
      }
    })

    // Set up map click callback - unified with Three.js measure/proximity
    mapboxService.onMapClick((lng: number, lat: number, screenX: number, screenY: number) => {
      // Check if proximity set mode is active (same check as Three.js)
      const isProximityMode = deps.containerRef.current?.dataset.proximityMode === 'true'
      if (isProximityMode && deps.onProximitySet) {
        deps.onProximitySet([lng, lat])
        return
      }

      // Check if measurement mode is active (same logic as Three.js)
      if (deps.measureModeRef.current && deps.onMeasurePointAddRef.current) {
        let finalLng = lng
        let finalLat = lat
        let snapped = false

        // Snap to nearest site or measurement point if snap is enabled (25px radius)
        if (deps.measureSnapEnabledRef.current) {
          // Gather all existing measurement points for snap checking
          const measurementPoints: Array<[number, number]> = []
          if (deps.measurementsRef.current) {
            deps.measurementsRef.current.forEach(m => {
              if (m.points) {
                measurementPoints.push([m.points[0][0], m.points[0][1]])
                measurementPoints.push([m.points[1][0], m.points[1][1]])
              }
            })
          }
          // Also check current measurement first point (if placing second point)
          if (deps.currentMeasurePointsRef.current && deps.currentMeasurePointsRef.current.length > 0) {
            const firstPoint = deps.currentMeasurePointsRef.current[0]
            if (firstPoint?.coords) {
              measurementPoints.push([firstPoint.coords[0], firstPoint.coords[1]])
            }
          }

          const snapTarget = mapboxService.findSnapTarget(screenX, screenY, 25, measurementPoints)
          console.log('[Mapbox Click] Snap check:', { snapEnabled: true, measurementPoints: measurementPoints.length, snapTarget })
          if (snapTarget) {
            finalLng = snapTarget[0]
            finalLat = snapTarget[1]
            snapped = true
          }
        }

        console.log('[Mapbox Click] Adding point:', { finalLng, finalLat, snapped })
        deps.onMeasurePointAddRef.current([finalLng, finalLat], snapped)
      } else {
        // Not in measure/proximity mode - clicking on empty space deselects all sites
        // Skip if a site was just clicked (site click callback fires first)
        if (!deps.siteClickJustHappenedRef.current && deps.onSiteSelectRef.current) {
          deps.onSiteSelectRef.current(null, false)
        }
      }
    })

    // Set up unified wheel zoom - wheel events update slider directly
    // This is the SAME as dragging the slider - ONE zoom system, no duplicates
    mapboxService.onWheelZoom((delta: number, cursorLatLng?: { lat: number; lng: number }) => {
      // Store cursor position for zoom-at-cursor
      deps.isWheelZoom.current = true
      deps.wheelCursorLatLng.current = cursorLatLng || null

      deps.setZoom(currentZoom => {
        return Math.max(0, Math.min(100, currentZoom + delta))
      })
    })

    // Now enable primary mode (callbacks are ready)
    deps.mapboxTransitioningRef.current = true
    mapboxService.enablePrimaryMode()

    // Set correct cursor based on current mode
    const isProximityMode = deps.containerRef.current?.dataset.proximityMode === 'true'
    if (deps.measureModeRef.current || isProximityMode) {
      mapboxService.setCursor('crosshair')
    } else {
      mapboxService.setCursor('grab')
    }

    // Hide Three.js dots AFTER the 300ms crossfade completes
    setTimeout(() => {
      deps.mapboxTransitioningRef.current = false
      if (points) points.visible = false
      if (backPoints) backPoints.visible = false
    }, 300)

  } else {
    // === EXITING MAPBOX MODE ===
    // Set isManualZoom to prevent animation loop from overriding slider value
    deps.isManualZoom.current = true

    // Sync only the look direction (lat/lng) from Mapbox, NOT the distance
    // The Three.js zoom effect will set the proper camera distance based on slider value
    const mapboxCamera = mapboxService.getCamera()

    console.log('[SYNC] === EXITING MAPBOX ===')
    console.log('[SYNC] Mapbox camera:', mapboxCamera)
    console.log('[SYNC] Current zoom slider:', deps.zoomRef.current)

    if (mapboxCamera) {
      // Get camera direction from Mapbox lat/lng (where user is looking)
      const centerPoint = latLngToCartesian(mapboxCamera.lat, mapboxCamera.lng, 1.0)
      const cameraDir = centerPoint.clone().normalize()

      // Calculate camera distance from slider value (not from Mapbox zoom)
      const currentSliderZoom = deps.zoomRef.current
      const scaledZoom = (currentSliderZoom / 66) * 80  // Match THREEJS_CAMERA_MAX
      const maxDist = CAMERA.MAX_DISTANCE  // 2.44
      const minDist = CAMERA.MIN_DISTANCE  // 1.02
      const targetDist = maxDist - (scaledZoom / 100) * (maxDist - minDist)

      // Position camera at slider-based distance, looking at Mapbox's lat/lng
      camera.position.copy(cameraDir.multiplyScalar(targetDist))
      camera.lookAt(0, 0, 0)
      controls.update()

      console.log('[SYNC] Three.js camera positioned at distance:', targetDist, 'for slider:', currentSliderZoom)
    }

    // Clear isManualZoom after a delay (let React settle)
    setTimeout(() => { deps.isManualZoom.current = false }, 300)

    // Show Three.js dots FIRST (before fade starts) for smooth crossfade
    if (points) points.visible = true
    if (backPoints) backPoints.visible = true

    // Re-enable Three.js controls
    controls.enabled = true

    // Now disable Mapbox primary mode (starts CSS fade-out over Three.js)
    mapboxService.disablePrimaryMode()

    // Clear callbacks
    mapboxService.onSiteClick(null)
    mapboxService.onSiteHover(null)
    mapboxService.onMouseMove(null)
    mapboxService.onMouseLeave(null)
    mapboxService.onCameraMove(null)
    mapboxService.onMapClick(null)
    mapboxService.onWheelZoom(null)

    // Clear any Mapbox-related tooltip state
    deps.setHoveredSite(null)
    deps.currentHoveredSiteRef.current = null

    // Clear coordinates (Three.js will update them on mousemove)
    deps.setCursorCoords(null)
  }
}

/**
 * Creates the Mapbox sites sync effect body.
 * Updates Mapbox site markers when sites or color mode changes.
 * Corresponds to Globe.tsx lines ~7447-7556.
 *
 * Usage in useEffect:
 *   useEffect(() => createSitesSyncEffect(deps), [showMapbox, sites, filterMode, sourceColors, countryColors, searchWithinProximity])
 */
export function createSitesSyncEffect(
  deps: SitesSyncEffectDeps
): void {
  const mapboxService = deps.mapboxServiceRef.current
  if (!mapboxService?.getIsInitialized() || !deps.showMapbox) return

  // Helper functions for color calculation (same as Three.js dots)
  const periodToYear = (period: string): number | null => {
    switch (period) {
      case '< 4500 BC': return -5000
      case '4500 - 3000 BC': return -3750
      case '3000 - 1500 BC': return -2250
      case '1500 - 500 BC': return -1000
      case '500 BC - 1 AD': return -250
      case '1 - 500 AD': return 250
      case '500 - 1000 AD': return 750
      case '1000 - 1500 AD': return 1250
      case '1500+ AD': return 1750
      default: return null
    }
  }

  const rgbToHex = (r: number, g: number, b: number): string => {
    return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('')
  }

  const getAgeColor = (year: number | null | undefined): string => {
    if (year === null || year === undefined) return '#9ca3af'
    const minYear = -5000
    const maxYear = 1500
    const clampedYear = Math.max(minYear, Math.min(maxYear, year))
    const t = (clampedYear - minYear) / (maxYear - minYear)
    // Bright red to yellow gradient (matching 3D globe)
    const colors = [
      { pos: 0, r: 255, g: 0, b: 0 },       // #ff0000 - bright red (oldest)
      { pos: 0.2, r: 255, g: 68, b: 0 },    // #ff4400 - orange-red
      { pos: 0.4, r: 255, g: 102, b: 0 },   // #ff6600 - orange
      { pos: 0.6, r: 255, g: 153, b: 0 },   // #ff9900 - orange
      { pos: 0.8, r: 255, g: 204, b: 0 },   // #ffcc00 - yellow-orange
      { pos: 1, r: 255, g: 255, b: 0 },     // #ffff00 - bright yellow (newest)
    ]
    let c1 = colors[0], c2 = colors[1]
    for (let i = 0; i < colors.length - 1; i++) {
      if (t >= colors[i].pos && t <= colors[i + 1].pos) {
        c1 = colors[i]
        c2 = colors[i + 1]
        break
      }
    }
    const localT = (t - c1.pos) / (c2.pos - c1.pos)
    const r = Math.round(c1.r + (c2.r - c1.r) * localT)
    const g = Math.round(c1.g + (c2.g - c1.g) * localT)
    const b = Math.round(c1.b + (c2.b - c1.b) * localT)
    return rgbToHex(r, g, b)
  }

  const extractCountry = (location: string | undefined): string => {
    if (!location) return 'Unknown'
    const parts = location.split(',')
    return parts[parts.length - 1].trim() || 'Unknown'
  }

  // Returns a validated hex color, falling back to gray if invalid
  const getColor = (site: SiteData): string => {
    const FALLBACK_COLOR = '#9ca3af'  // Safe gray fallback
    let color: string | undefined

    switch (deps.filterMode) {
      case 'source':
        color = deps.sourceColors?.[site.sourceId] || SOURCE_COLORS[site.sourceId] || SOURCE_COLORS.default || FALLBACK_COLOR
        break
      case 'category':
        color = getCategoryColor(site.category)
        break
      case 'country':
        const country = extractCountry(site.location)
        color = deps.countryColors?.[country] || '#a855f7'
        break
      case 'age':
      default:
        const year = site.periodStart ?? periodToYear(site.period)
        color = getAgeColor(year)
        break
    }

    // Validate hex format - return fallback if invalid to prevent black dots
    if (!color || !/^#[0-9A-Fa-f]{6}$/.test(color)) {
      return FALLBACK_COLOR
    }
    return color
  }

  // Convert sites to Mapbox format with proper colors
  // Also filter by proximity when searchWithinProximity is enabled
  const mapboxSites: MapboxMarkerData[] = deps.sites
    .filter(site => {
      const coords = site.coordinates
      if (!coords || !Array.isArray(coords) || coords.length < 2) return false
      if (typeof coords[0] !== 'number' || typeof coords[1] !== 'number') return false
      // Filter out sites outside proximity when "Within proximity" is checked
      if (deps.searchWithinProximity && site.isInsideProximity === false) return false
      return true
    })
    .map(site => ({
      id: site.id,
      longitude: site.coordinates[0],
      latitude: site.coordinates[1],
      color: getColor(site)
    }))

  mapboxService.setSites(mapboxSites)
}

/**
 * Creates the Mapbox measurements sync effect body.
 * Syncs measurement lines and points to Mapbox when in Mapbox mode.
 * Corresponds to Globe.tsx lines ~7559-7646.
 *
 * Usage in useEffect:
 *   useEffect(() => createMeasurementsSyncEffect(deps), [showMapbox, measurements, currentMeasurePoints, measureUnit])
 */
export function createMeasurementsSyncEffect(
  deps: MeasurementsSyncEffectDeps
): void {
  const mapboxService = deps.mapboxServiceRef.current
  if (!mapboxService?.getIsInitialized()) return

  if (!deps.showMapbox) {
    mapboxService.clearMeasurements()
    return
  }

  // Haversine distance calculation for labels
  const calcDistance = (lng1: number, lat1: number, lng2: number, lat2: number): number => {
    const R = 6371 // Earth radius in km
    const dLat = (lat2 - lat1) * Math.PI / 180
    const dLng = (lng2 - lng1) * Math.PI / 180
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLng/2) * Math.sin(dLng/2)
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a))
  }

  // Format distance label
  const formatDistance = (km: number): string => {
    if (deps.measureUnit === 'miles') {
      return `${(km * 0.621371).toFixed(1)} mi`
    }
    return `${km.toFixed(1)} km`
  }

  // Combine completed measurements with current measurement in progress
  const allMeasurements: Array<{
    id: string
    start: [number, number]
    end: [number, number]
    color: string
    label?: string
    startSnapped?: boolean
    endSnapped?: boolean
  }> = []

  // Add completed measurements with labels and snapped info
  if (deps.measurements && deps.measurements.length > 0) {
    deps.measurements.forEach((m) => {
      const dist = calcDistance(m.points[0][0], m.points[0][1], m.points[1][0], m.points[1][1])
      allMeasurements.push({
        id: m.id,
        start: [m.points[0][0], m.points[0][1]],
        end: [m.points[1][0], m.points[1][1]],
        color: m.color,
        label: formatDistance(dist),
        startSnapped: m.snapped?.[0] ?? false,
        endSnapped: m.snapped?.[1] ?? false
      })
    })
  }

  // Add current measurement in progress (if 2 points)
  if (deps.currentMeasurePoints && deps.currentMeasurePoints.length === 2) {
    const dist = calcDistance(
      deps.currentMeasurePoints[0].coords[0], deps.currentMeasurePoints[0].coords[1],
      deps.currentMeasurePoints[1].coords[0], deps.currentMeasurePoints[1].coords[1]
    )
    allMeasurements.push({
      id: 'current',
      start: [deps.currentMeasurePoints[0].coords[0], deps.currentMeasurePoints[0].coords[1]],
      end: [deps.currentMeasurePoints[1].coords[0], deps.currentMeasurePoints[1].coords[1]],
      color: '#f59e0b',  // Amber/yellow for current measurement
      label: formatDistance(dist),
      startSnapped: deps.currentMeasurePoints[0].snapped ?? false,
      endSnapped: deps.currentMeasurePoints[1].snapped ?? false
    })
  }

  // Build single points array (for first point of in-progress measurement)
  const singlePoints: Array<{ coords: [number, number]; color: string; snapped: boolean }> = []
  if (deps.currentMeasurePoints && deps.currentMeasurePoints.length === 1) {
    singlePoints.push({
      coords: [deps.currentMeasurePoints[0].coords[0], deps.currentMeasurePoints[0].coords[1]],
      color: '#f59e0b',  // Amber/yellow for current measurement
      snapped: deps.currentMeasurePoints[0].snapped ?? false
    })
  }

  if (allMeasurements.length > 0 || singlePoints.length > 0) {
    mapboxService.setMeasurementLines(allMeasurements, singlePoints)
  } else {
    mapboxService.clearMeasurements()
  }
}

/**
 * Creates the Mapbox proximity circle sync effect body.
 * Syncs proximity circle to Mapbox when in Mapbox mode.
 * Corresponds to Globe.tsx lines ~7649-7663.
 *
 * Usage in useEffect:
 *   useEffect(() => createProximityCircleSyncEffect(deps), [showMapbox, proximity?.center, proximity?.radius])
 */
export function createProximityCircleSyncEffect(
  deps: ProximityCircleSyncEffectDeps
): void {
  const mapboxService = deps.mapboxServiceRef.current
  if (!mapboxService?.getIsInitialized()) return

  if (deps.showMapbox && deps.proximity?.center) {
    // Use 10km default in Mapbox mode (more appropriate for zoomed-in view)
    mapboxService.setProximityCircle(
      [deps.proximity.center[0], deps.proximity.center[1]],
      deps.proximity.radius || 10
    )
  } else {
    // Clear proximity when not in Mapbox mode or no center set
    mapboxService.clearProximityCircle()
  }
}

/**
 * Creates the Mapbox frozen/selected sites sync effect body.
 * Syncs selected sites (green rings) to Mapbox when in Mapbox mode.
 * Corresponds to Globe.tsx lines ~7666-7683.
 *
 * Usage in useEffect:
 *   useEffect(() => createSelectedSitesSyncEffect(deps), [showMapbox, listFrozenSiteIds])
 */
export function createSelectedSitesSyncEffect(
  deps: SelectedSitesSyncEffectDeps
): void {
  const mapboxService = deps.mapboxServiceRef.current
  if (!mapboxService?.getIsInitialized()) return

  if (deps.showMapbox && deps.listFrozenSiteIds.length > 0) {
    // Get coordinates for selected sites
    const selectedSites = deps.listFrozenSiteIds
      .map(id => {
        const site = deps.sitesRef.current.find(s => s.id === id)
        return site ? { id: site.id, lng: site.coordinates[0], lat: site.coordinates[1] } : null
      })
      .filter((s): s is { id: string; lng: number; lat: number } => s !== null)

    mapboxService.setSelectedSites(selectedSites)
  } else {
    mapboxService.clearSelectedSites()
  }
}
