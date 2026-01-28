/**
 * useMapboxSync - Three.js ↔ Mapbox camera synchronization
 * Manages the transition and sync between Three.js globe and Mapbox map modes
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import type * as THREE from 'three'
import type { MapboxGlobeService } from '../../services/MapboxGlobeService'

interface MapboxSyncCallbacks {
  // Mode change notification
  onModeChange?: (isMapboxMode: boolean) => void

  // Called when entering Mapbox mode - for setting up event handlers
  onEnterMapboxMode?: (mapboxService: MapboxGlobeService) => void

  // Called when exiting Mapbox mode - for cleanup
  onExitMapboxMode?: (mapboxService: MapboxGlobeService) => void

  // Called to get Three.js view data for syncing to Mapbox
  getThreeJsView?: () => { lat: number; lng: number; zoom: number } | null

  // Called to apply Mapbox camera state back to Three.js
  applyMapboxCameraToThreeJs?: (lat: number, lng: number, zoom: number) => void

  // Called when auto-switch threshold is crossed
  onAutoSwitchToMapbox?: () => void
  onAutoSwitchToThreeJs?: () => void

  // Offline warning callback
  onShowOfflineWarning?: (show: boolean) => void
}

interface MapboxSyncOptions {
  mapboxServiceRef: React.MutableRefObject<MapboxGlobeService | null>
  camera?: THREE.PerspectiveCamera | null
  minDist?: number
  maxDist?: number
  transitionPoint?: number  // Zoom level to transition (default 66)
  callbacks?: MapboxSyncCallbacks

  // Offline mode
  isOffline?: boolean
  hasMapboxTilesCached?: boolean
}

export function useMapboxSync(options: MapboxSyncOptions) {
  const {
    mapboxServiceRef,
    camera,
    minDist = 1.02,
    maxDist = 2.44,
    transitionPoint = 66,
    callbacks = {},
    isOffline = false,
    hasMapboxTilesCached = false
  } = options

  const {
    onModeChange,
    onEnterMapboxMode,
    onExitMapboxMode,
    getThreeJsView,
    applyMapboxCameraToThreeJs,
    onAutoSwitchToMapbox,
    onAutoSwitchToThreeJs,
    onShowOfflineWarning
  } = callbacks

  // Mapbox visibility
  const [showMapbox, setShowMapbox] = useState(false)
  const showMapboxRef = useRef(false)

  // Transition state
  const [isTransitioning, setIsTransitioning] = useState(false)
  const mapboxTransitioningRef = useRef(false)

  // Track if we just entered Mapbox mode (to skip first zoom update)
  const justEnteredMapbox = useRef(false)

  // Track Mapbox base zoom (zoom level after camera sync)
  const mapboxBaseZoomRef = useRef(50)

  // Track zoom source to prevent feedback loops
  const isMapboxZoom = useRef(false)
  const isSliderZoom = useRef(false)
  const isWheelZoom = useRef(false)
  const wheelCursorLatLng = useRef<{ lat: number; lng: number } | null>(null)

  // Track previous showMapbox to detect actual mode changes
  const prevShowMapboxRef = useRef(false)

  // Satellite mode state (dark vs satellite tiles)
  const [satelliteMode, setSatelliteMode] = useState(false)
  const satelliteModeRef = useRef(false)

  // Offline warning state
  const [showMapboxOfflineWarning, setShowMapboxOfflineWarning] = useState(false)

  // Sync showMapbox state with ref and notify callback
  useEffect(() => {
    const modeActuallyChanged = prevShowMapboxRef.current !== showMapbox
    prevShowMapboxRef.current = showMapbox
    showMapboxRef.current = showMapbox

    if (modeActuallyChanged) {
      onModeChange?.(showMapbox)
    }
  }, [showMapbox, onModeChange])

  // Sync satellite mode state with ref
  useEffect(() => {
    satelliteModeRef.current = satelliteMode
  }, [satelliteMode])

  // Get camera lat/lng for Mapbox sync
  const getCameraLatLng = useCallback(() => {
    if (!camera) return null

    const direction = camera.position.clone().normalize().negate()

    // Convert direction to lat/lng
    const lat = Math.asin(direction.y) * (180 / Math.PI)
    const lng = Math.atan2(direction.z, direction.x) * (180 / Math.PI) - 180

    return { lat, lng }
  }, [camera])

  // Calculate zoom percent from camera distance
  const getZoomFromCamera = useCallback(() => {
    if (!camera) return 0

    const dist = camera.position.length()
    const scaledZoom = ((maxDist - dist) / (maxDist - minDist)) * 100
    return Math.max(0, Math.min(66, (scaledZoom / 80) * 66))
  }, [camera, minDist, maxDist])

  // Sync Three.js camera to Mapbox
  const syncToMapbox = useCallback(() => {
    const mapbox = mapboxServiceRef.current
    if (!mapbox?.getIsInitialized() || !camera) return

    const latLng = getCameraLatLng()
    if (!latLng) return

    const zoomPercent = getZoomFromCamera()

    // Scale to Mapbox zoom (66% Three.js = base Mapbox zoom)
    const mapboxZoom = (zoomPercent / transitionPoint) * 50  // Rough mapping
    mapboxBaseZoomRef.current = mapboxZoom

    mapbox.setCamera(latLng.lat, latLng.lng, mapboxZoom)
    mapbox.setZoomPercent(mapboxZoom)
  }, [mapboxServiceRef, camera, getCameraLatLng, getZoomFromCamera, transitionPoint])

  // Sync Mapbox to Three.js camera
  const syncFromMapbox = useCallback(() => {
    const mapbox = mapboxServiceRef.current
    if (!mapbox?.getIsInitialized() || !camera) return

    const cameraData = mapbox.getCamera()
    if (!cameraData) return

    // Convert Mapbox center to camera position
    const lat = cameraData.lat
    const lng = cameraData.lng
    const phi = (90 - lat) * Math.PI / 180
    const theta = (lng + 180) * Math.PI / 180

    const dist = camera.position.length()
    const x = -Math.sin(phi) * Math.cos(theta) * dist
    const y = Math.cos(phi) * dist
    const z = Math.sin(phi) * Math.sin(theta) * dist

    camera.position.set(x, y, z)
    camera.lookAt(0, 0, 0)
  }, [mapboxServiceRef, camera])

  // Enter Mapbox mode
  const enterMapboxMode = useCallback(() => {
    if (showMapbox) return

    const mapbox = mapboxServiceRef.current
    if (!mapbox?.getIsInitialized()) return

    setIsTransitioning(true)
    mapboxTransitioningRef.current = true
    justEnteredMapbox.current = true

    // Get Three.js view for syncing to Mapbox
    const view = getThreeJsView?.()
    if (view) {
      mapbox.setCamera(view.lat, view.lng, view.zoom)
      // Store base zoom percent for incremental zooming
      const MAPBOX_FULL_ZOOM_MIN = 0.7
      const MAPBOX_FULL_ZOOM_MAX = 18
      mapboxBaseZoomRef.current = ((view.zoom - MAPBOX_FULL_ZOOM_MIN) / (MAPBOX_FULL_ZOOM_MAX - MAPBOX_FULL_ZOOM_MIN)) * 100
    } else {
      // Fallback to basic sync
      syncToMapbox()
    }

    // Enable Mapbox primary mode (triggers CSS transition)
    mapboxTransitioningRef.current = true
    mapbox.enablePrimaryMode()

    // Call callback for setting up event handlers
    onEnterMapboxMode?.(mapbox)

    // After transition completes
    setTimeout(() => {
      setShowMapbox(true)
      mapboxTransitioningRef.current = false
    }, 300)  // Match CSS transition duration
  }, [showMapbox, mapboxServiceRef, syncToMapbox, getThreeJsView, onEnterMapboxMode])

  // Exit Mapbox mode
  const exitMapboxMode = useCallback(() => {
    if (!showMapbox) return

    const mapbox = mapboxServiceRef.current
    if (!mapbox?.getIsInitialized()) return

    setIsTransitioning(true)
    mapboxTransitioningRef.current = true

    // Get Mapbox camera state and sync back to Three.js
    const mapboxCamera = mapbox.getCamera()
    if (mapboxCamera && applyMapboxCameraToThreeJs) {
      applyMapboxCameraToThreeJs(mapboxCamera.lat, mapboxCamera.lng, mapboxCamera.zoom)
    } else {
      // Fallback to basic sync
      syncFromMapbox()
    }

    // Call callback for cleanup before disabling
    onExitMapboxMode?.(mapbox)

    // Disable Mapbox primary mode (triggers CSS fade-out)
    mapbox.disablePrimaryMode()

    setTimeout(() => {
      setShowMapbox(false)
      setIsTransitioning(false)
      mapboxTransitioningRef.current = false
    }, 100)
  }, [showMapbox, mapboxServiceRef, syncFromMapbox, applyMapboxCameraToThreeJs, onExitMapboxMode])

  // Toggle Mapbox mode
  const toggleMapboxMode = useCallback(() => {
    if (showMapbox) {
      exitMapboxMode()
    } else {
      enterMapboxMode()
    }
  }, [showMapbox, enterMapboxMode, exitMapboxMode])

  // Handle zoom change for auto-switch logic
  // Called from animation loop or zoom slider
  const handleZoomChange = useCallback((zoomPercent: number) => {
    const mapbox = mapboxServiceRef.current
    if (!mapbox?.getIsInitialized()) return

    // Auto-switch: zoom >= 66% switches to Mapbox, < 66% switches to Three.js
    if (zoomPercent >= transitionPoint && !showMapbox) {
      console.log('[AUTO-SWITCH] Zoom >= 66%, switching to Mapbox')
      justEnteredMapbox.current = true
      setShowMapbox(true)
      onAutoSwitchToMapbox?.()

      // Show offline warning if applicable
      if (isOffline && !hasMapboxTilesCached) {
        setShowMapboxOfflineWarning(true)
        onShowOfflineWarning?.(true)
      }
    } else if (zoomPercent < transitionPoint && showMapbox) {
      console.log('[AUTO-SWITCH] Zoom < 66%, switching to Three.js')
      setShowMapbox(false)
      setShowMapboxOfflineWarning(false)
      onShowOfflineWarning?.(false)
      onAutoSwitchToThreeJs?.()
    }
  }, [showMapbox, mapboxServiceRef, transitionPoint, isOffline, hasMapboxTilesCached, onAutoSwitchToMapbox, onAutoSwitchToThreeJs, onShowOfflineWarning])

  // Update Mapbox zoom from slider (66-100% range)
  const updateMapboxZoom = useCallback((zoomPercent: number) => {
    const mapbox = mapboxServiceRef.current
    if (!mapbox?.getIsInitialized() || !showMapbox) return

    // Skip first update after entering Mapbox (camera sync already positioned it)
    if (justEnteredMapbox.current) {
      justEnteredMapbox.current = false
      return
    }

    // Don't update if this came from Mapbox interaction (avoid feedback loop)
    if (isMapboxZoom.current) {
      isMapboxZoom.current = false
      return
    }

    // Scale 66-100 to Mapbox zoom INCREASE from base position
    const sliderProgress = (zoomPercent - transitionPoint) / (100 - transitionPoint)  // 0 at 66%, 1 at 100%
    const baseZoom = mapboxBaseZoomRef.current

    // At 100% slider = max zoom increase (about 50% more than base)
    const zoomIncrease = sliderProgress * 50
    const targetZoom = Math.min(100, baseZoom + zoomIncrease)

    // Use zoom at cursor if wheel zoom
    if (isWheelZoom.current && wheelCursorLatLng.current) {
      mapbox.setZoomPercentAtPoint(targetZoom, wheelCursorLatLng.current)
    } else {
      mapbox.setZoomPercent(targetZoom)
    }

    // Reset flags after a short delay (after Mapbox fires its callback)
    setTimeout(() => {
      isSliderZoom.current = false
      isWheelZoom.current = false
    }, 100)
  }, [showMapbox, mapboxServiceRef, transitionPoint])

  // Update Mapbox tile style (dark vs satellite)
  const updateMapboxStyle = useCallback(() => {
    const mapbox = mapboxServiceRef.current
    if (!mapbox?.getIsInitialized()) return

    const tileType = satelliteModeRef.current ? 'satellite' : 'dark'
    if (mapbox.getStyle() !== tileType) {
      console.log(`[Mapbox] Switching style: ${mapbox.getStyle()} -> ${tileType}`)
      mapbox.setStyle(tileType)
    }
  }, [mapboxServiceRef])

  // Dismiss offline warning
  const dismissOfflineWarning = useCallback(() => {
    setShowMapboxOfflineWarning(false)
    onShowOfflineWarning?.(false)
  }, [onShowOfflineWarning])

  return {
    // State
    showMapbox,
    setShowMapbox,
    showMapboxRef,
    isTransitioning,
    mapboxTransitioningRef,
    prevShowMapboxRef,

    // Entry/exit tracking
    justEnteredMapbox,
    mapboxBaseZoomRef,

    // Zoom source tracking
    isMapboxZoom,
    isSliderZoom,
    isWheelZoom,
    wheelCursorLatLng,

    // Satellite mode
    satelliteMode,
    setSatelliteMode,
    satelliteModeRef,

    // Offline warning
    showMapboxOfflineWarning,
    setShowMapboxOfflineWarning,
    dismissOfflineWarning,

    // Sync methods
    syncToMapbox,
    syncFromMapbox,
    getCameraLatLng,
    getZoomFromCamera,

    // Mode control
    enterMapboxMode,
    exitMapboxMode,
    toggleMapboxMode,

    // Auto-switch and zoom
    handleZoomChange,
    updateMapboxZoom,
    updateMapboxStyle
  }
}
