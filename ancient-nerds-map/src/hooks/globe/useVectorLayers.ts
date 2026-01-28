/**
 * useVectorLayers - Vector layer loading and management
 * Manages front/back layer loading with chunked processing
 */

import { useState, useCallback, useRef } from 'react'
import type * as THREE from 'three'
import {
  LAYER_CONFIG,
  getLayerUrl,
  type VectorLayerKey,
  type VectorLayerVisibility
} from '../../config/vectorLayers'
import { type DetailLevel } from '../../config/globeConstants'

interface VectorLayerRefs {
  front: THREE.Object3D[]
  back: THREE.Object3D[]
}

interface LayerLoadResult {
  frontLines: THREE.Line[]
  backLines: THREE.Line[]
  labels?: THREE.Object3D[]
}

interface UseVectorLayersOptions {
  scene: THREE.Scene | null
  globe: THREE.Group | null
  isOffline?: boolean
  cachedLayerIds?: Set<string>
  // Optional custom processor - if provided, the hook will call this
  // instead of its default (stub) processing
  processGeoJSON?: (
    key: VectorLayerKey,
    geojson: any,
    detailLevel: DetailLevel,
    abortSignal: AbortSignal
  ) => Promise<LayerLoadResult | null>
  // Callback when layer loading starts/ends
  onLayerLoadStart?: (key: VectorLayerKey) => void
  onLayerLoadEnd?: (key: VectorLayerKey, success: boolean) => void
  // Callback when layer visibility changes
  onLayerVisibilityChange?: (key: VectorLayerKey, visible: boolean) => void
}

const DEFAULT_VISIBILITY: VectorLayerVisibility = {
  coastlines: true,
  countryBorders: false,
  rivers: false,
  lakes: false,
  plateBoundaries: false,
  glaciers: false,
  coralReefs: false
}

export function useVectorLayers(options: UseVectorLayersOptions) {
  const {
    scene,
    globe,
    isOffline = false,
    cachedLayerIds = new Set(),
    processGeoJSON,
    onLayerLoadStart,
    onLayerLoadEnd,
    onLayerVisibilityChange,
  } = options

  // Layer visibility state
  const [vectorLayers, setVectorLayers] = useState<VectorLayerVisibility>(DEFAULT_VISIBILITY)

  // Loading state for each layer
  const [isLoadingLayers, setIsLoadingLayers] = useState<Record<string, boolean>>({})

  // Detail level for LOD
  const [detailLevel, setDetailLevel] = useState<DetailLevel>('ultra-low')
  const detailLevelRef = useRef<DetailLevel>('ultra-low')

  // Layer object refs
  const layerRefsRef = useRef<Record<string, VectorLayerRefs>>({})

  // Labels per layer
  const layerLabelsRef = useRef<Record<string, THREE.Object3D[]>>({})

  // Track current layer loading operations for cancellation
  const layerAbortControllersRef = useRef<Record<string, AbortController>>({})

  // Toggle a layer
  const toggleLayer = useCallback((key: VectorLayerKey) => {
    setVectorLayers(prev => {
      const newVisible = !prev[key]
      onLayerVisibilityChange?.(key, newVisible)
      return {
        ...prev,
        [key]: newVisible
      }
    })
  }, [onLayerVisibilityChange])

  // Set a specific layer visibility
  const setLayerVisibility = useCallback((key: VectorLayerKey, visible: boolean) => {
    setVectorLayers(prev => {
      if (prev[key] !== visible) {
        onLayerVisibilityChange?.(key, visible)
      }
      return {
        ...prev,
        [key]: visible
      }
    })
  }, [onLayerVisibilityChange])

  // Load a single layer
  const loadLayer = useCallback(async (key: VectorLayerKey) => {
    if (!scene || !globe) return

    const config = LAYER_CONFIG[key]
    if (!config) return

    // Cancel any existing load for this layer
    if (layerAbortControllersRef.current[key]) {
      layerAbortControllersRef.current[key].abort()
    }

    // Create new abort controller
    const abortController = new AbortController()
    layerAbortControllersRef.current[key] = abortController

    setIsLoadingLayers(prev => ({ ...prev, [key]: true }))
    onLayerLoadStart?.(key)

    let success = false
    try {
      // Get appropriate data URL based on detail level
      const dataUrl = getLayerUrl(key, detailLevelRef.current)

      const response = await fetch(dataUrl, { signal: abortController.signal })
      if (!response.ok) throw new Error(`Failed to load ${key}`)

      const geojson = await response.json()

      // Clean up previous objects
      const prevRefs = layerRefsRef.current[key]
      if (prevRefs) {
        prevRefs.front.forEach(obj => {
          globe.remove(obj)
          if ((obj as any).geometry) (obj as any).geometry.dispose()
          if ((obj as any).material) (obj as any).material.dispose()
        })
        prevRefs.back.forEach(obj => {
          globe.remove(obj)
          if ((obj as any).geometry) (obj as any).geometry.dispose()
          if ((obj as any).material) (obj as any).material.dispose()
        })
      }

      // Process features using custom processor if provided
      if (processGeoJSON) {
        const result = await processGeoJSON(key, geojson, detailLevelRef.current, abortController.signal)
        if (result) {
          layerRefsRef.current[key] = {
            front: result.frontLines,
            back: result.backLines
          }
          if (result.labels) {
            layerLabelsRef.current[key] = result.labels
          }
          success = true
        }
      } else {
        // Default stub processing - actual implementation deferred to Globe.tsx
        layerRefsRef.current[key] = {
          front: [],
          back: []
        }
        success = true
      }

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Cancelled, not an error
        return
      }
      console.error(`Failed to load layer ${key}:`, error)
    } finally {
      setIsLoadingLayers(prev => ({ ...prev, [key]: false }))
      onLayerLoadEnd?.(key, success)
    }
  }, [scene, globe, processGeoJSON, onLayerLoadStart, onLayerLoadEnd])

  // Unload a layer
  const unloadLayer = useCallback((key: VectorLayerKey) => {
    if (!globe) return

    // Cancel any pending load
    if (layerAbortControllersRef.current[key]) {
      layerAbortControllersRef.current[key].abort()
      delete layerAbortControllersRef.current[key]
    }

    // Remove objects
    const refs = layerRefsRef.current[key]
    if (refs) {
      refs.front.forEach(obj => {
        globe.remove(obj)
        if ((obj as any).geometry) (obj as any).geometry.dispose()
        if ((obj as any).material) (obj as any).material.dispose()
      })
      refs.back.forEach(obj => {
        globe.remove(obj)
        if ((obj as any).geometry) (obj as any).geometry.dispose()
        if ((obj as any).material) (obj as any).material.dispose()
      })
      delete layerRefsRef.current[key]
    }

    // Remove labels
    const labels = layerLabelsRef.current[key]
    if (labels && scene) {
      labels.forEach(label => {
        scene.remove(label)
        if ((label as any).geometry) (label as any).geometry.dispose()
        if ((label as any).material) {
          const mat = (label as any).material
          if (mat.map) mat.map.dispose()
          mat.dispose()
        }
      })
      delete layerLabelsRef.current[key]
    }
  }, [scene, globe])

  // Update detail level
  const updateDetailLevel = useCallback((zoom: number) => {
    const getDetailFromZoom = (zoomPercent: number): DetailLevel => {
      if (zoomPercent < 25) return 'ultra-low'
      if (zoomPercent < 50) return 'low'
      if (zoomPercent < 75) return 'medium'
      return 'high'
    }

    const newDetail = getDetailFromZoom(zoom)
    if (newDetail !== detailLevelRef.current) {
      detailLevelRef.current = newDetail
      setDetailLevel(newDetail)
    }
  }, [])

  // Check if layer is available offline
  const isLayerAvailableOffline = useCallback((key: VectorLayerKey) => {
    if (!isOffline) return true
    return cachedLayerIds.has(key)
  }, [isOffline, cachedLayerIds])

  return {
    // State
    vectorLayers,
    setVectorLayers,
    isLoadingLayers,
    detailLevel,

    // Actions
    toggleLayer,
    setLayerVisibility,
    loadLayer,
    unloadLayer,
    updateDetailLevel,
    isLayerAvailableOffline,

    // Refs
    layerRefsRef,
    layerLabelsRef,
    detailLevelRef
  }
}
