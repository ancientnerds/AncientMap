/**
 * useGlobeZoom - Hook for managing zoom state and camera control
 *
 * Consolidates:
 * - Zoom state and refs
 * - Detail level calculation
 * - Three.js camera zoom (0-66%)
 * - Mapbox zoom (66-100%)
 * - Play button sync with zoom state
 */

import { useEffect, useState, useCallback } from 'react'
import type { GlobeRefs } from './types'
import { CAMERA, type DetailLevel } from '../../config/globeConstants'

// Zoom slider constants
const THREEJS_MAX_ZOOM = 66    // Three.js controls 0-66% of slider (matches transition point)
const MAPBOX_MIN_ZOOM = 66     // Mapbox controls 66-100% of slider
const THREEJS_CAMERA_MAX = 80  // At 66% slider, camera is at 80% of range

interface UseGlobeZoomOptions {
  refs: GlobeRefs
  showMapbox: boolean
}

interface UseGlobeZoomReturn {
  zoom: number
  setZoom: (updater: number | ((prev: number) => number)) => void
  detailLevel: DetailLevel
  isZoomedIn: boolean
}

/**
 * Helper to calculate detail level from zoom percentage
 */
function getDetailFromZoom(zoomPercent: number): DetailLevel {
  if (zoomPercent < 25) return 'ultra-low'
  if (zoomPercent < 50) return 'low'
  if (zoomPercent < 75) return 'medium'
  return 'high'
}

export function useGlobeZoom({ refs, showMapbox }: UseGlobeZoomOptions): UseGlobeZoomReturn {
  const [zoom, setZoomState] = useState(0)
  const [detailLevel, setDetailLevel] = useState<DetailLevel>('medium')

  // Sync zoom to ref for event handlers
  useEffect(() => {
    refs.zoom.current = zoom
  }, [zoom, refs.zoom])

  // Wrapper to set zoom (can be used by external components)
  // Supports both direct values and updater functions like useState
  const setZoom = useCallback((updater: number | ((prev: number) => number)) => {
    setZoomState(updater)
  }, [])

  // Update Three.js camera when zoom is 0-66%
  useEffect(() => {
    const scene = refs.scene.current
    if (!scene) return
    if (zoom > THREEJS_MAX_ZOOM) return  // Above 66%, Mapbox handles it

    const { camera, controls } = scene

    const maxDist = CAMERA.MAX_DISTANCE  // 2.44
    const minDist = CAMERA.MIN_DISTANCE  // 1.02

    // Scale 0-66% slider to full camera range
    // At slider 66%, camera is at closest position (100% of zoom range)
    const scaledZoom = (zoom / THREEJS_MAX_ZOOM) * THREEJS_CAMERA_MAX
    const targetDist = maxDist - (scaledZoom / 100) * (maxDist - minDist)

    refs.isManualZoom.current = true

    const direction = camera.position.clone().sub(controls.target).normalize()
    camera.position.copy(controls.target).add(direction.multiplyScalar(targetDist))

    controls.rotateSpeed = Math.max(0.1, 0.5 - (scaledZoom / 100) * 0.4)

    controls.update()

    setTimeout(() => { refs.isManualZoom.current = false }, 300)
  }, [zoom, refs.scene, refs.isManualZoom])

  // Update Mapbox zoom when zoom is 66-100%
  useEffect(() => {
    const mapboxService = refs.mapboxService.current
    if (!mapboxService?.getIsInitialized()) return
    if (zoom < MAPBOX_MIN_ZOOM) return  // Three.js handles 0-65%
    if (!showMapbox) return  // Only update when in Mapbox mode

    // Skip first update after entering Mapbox (camera sync already positioned it correctly)
    if (refs.justEnteredMapbox.current) {
      refs.justEnteredMapbox.current = false
      return
    }

    // Don't update if this came from Mapbox interaction (avoid feedback loop)
    if (refs.isMapboxZoom.current) {
      refs.isMapboxZoom.current = false
      return
    }

    // Scale 66-100 to Mapbox zoom INCREASE from base position
    // At 66%: stay at base zoom (where camera sync put us)
    // At 100%: maximum zoom (100%)
    const baseZoom = refs.mapboxBaseZoom.current  // Actual zoom level after camera sync
    const remainingZoomRange = 100 - baseZoom  // How much more zoom is available
    const sliderProgress = (zoom - MAPBOX_MIN_ZOOM) / (100 - MAPBOX_MIN_ZOOM)  // 0 to 1
    const targetZoom = Math.min(100, baseZoom + sliderProgress * remainingZoomRange)

    // Set flag to prevent callback from updating slider
    refs.isSliderZoom.current = true

    // Use zoom-at-cursor if this came from wheel zoom with cursor position
    if (refs.isWheelZoom.current && refs.wheelCursorLatLng.current) {
      mapboxService.setZoomPercentAtPoint(targetZoom, refs.wheelCursorLatLng.current)
    } else {
      mapboxService.setZoomPercent(targetZoom)
    }

    // Reset flags after a short delay (after Mapbox fires its callback)
    setTimeout(() => {
      refs.isSliderZoom.current = false
      refs.isWheelZoom.current = false
      refs.wheelCursorLatLng.current = null
    }, 100)
  }, [zoom, showMapbox, refs.mapboxService, refs.justEnteredMapbox, refs.isMapboxZoom, refs.mapboxBaseZoom, refs.isSliderZoom, refs.isWheelZoom, refs.wheelCursorLatLng])

  // Calculate detail level from zoom percentage (for rivers/lakes LOD)
  useEffect(() => {
    const newDetail = getDetailFromZoom(zoom)
    if (newDetail !== refs.detailLevel.current) {
      refs.detailLevel.current = newDetail
      setDetailLevel(newDetail)
    }
  }, [zoom, refs.detailLevel])

  // Compute derived values
  const isZoomedIn = zoom >= 34

  return {
    zoom,
    setZoom,
    detailLevel,
    isZoomedIn,
  }
}
