/**
 * useProximityFilter - Proximity circle logic and state
 * Manages proximity filter state including center point, radius, and preview
 */

import { useState, useCallback, useRef } from 'react'
import type * as THREE from 'three'

interface ProximityState {
  center: [number, number] | null  // [lat, lng]
  radius: number  // km
  enabled: boolean
}

interface ProximityFilterOptions {
  initialRadius?: number
  initialEnabled?: boolean
}

export function useProximityFilter(options: ProximityFilterOptions = {}) {
  const {
    initialRadius = 100,
    initialEnabled = false
  } = options

  // Proximity state
  const [proximity, setProximity] = useState<ProximityState>({
    center: null,
    radius: initialRadius,
    enabled: initialEnabled
  })

  // Preview state (when dragging radius or positioning)
  const [proximityPreview, setProximityPreview] = useState<{
    center: [number, number]
    radius: number
  } | null>(null)

  // Search within proximity toggle
  const [searchWithinProximity, setSearchWithinProximity] = useState(false)

  // Refs for 3D objects (crosshair, ring)
  const proximityCenterRef = useRef<THREE.Sprite | null>(null)
  const proximityRingRef = useRef<THREE.Line | null>(null)

  // Set center point
  const setProximityCenter = useCallback((lat: number, lng: number) => {
    setProximity(prev => ({
      ...prev,
      center: [lat, lng],
      enabled: true
    }))
  }, [])

  // Set radius
  const setProximityRadius = useCallback((radius: number) => {
    setProximity(prev => ({
      ...prev,
      radius: Math.max(1, Math.min(20000, radius))  // 1km to 20,000km
    }))
  }, [])

  // Clear proximity filter
  const clearProximity = useCallback(() => {
    setProximity({
      center: null,
      radius: initialRadius,
      enabled: false
    })
    setProximityPreview(null)
    setSearchWithinProximity(false)
  }, [initialRadius])

  // Toggle enabled
  const toggleProximity = useCallback(() => {
    setProximity(prev => ({
      ...prev,
      enabled: !prev.enabled
    }))
  }, [])

  // Toggle search within proximity
  const toggleSearchWithinProximity = useCallback(() => {
    setSearchWithinProximity(prev => !prev)
  }, [])

  return {
    // Main state
    proximity,
    setProximity,
    setProximityCenter,
    setProximityRadius,
    clearProximity,
    toggleProximity,

    // Preview state
    proximityPreview,
    setProximityPreview,

    // Search toggle
    searchWithinProximity,
    setSearchWithinProximity,
    toggleSearchWithinProximity,

    // 3D object refs
    proximityCenterRef,
    proximityRingRef
  }
}
