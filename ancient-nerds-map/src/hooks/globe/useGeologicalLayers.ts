/**
 * useGeologicalLayers - State management for geological overlay layers
 * Manages visibility and loading state for North Sea geological data
 */

import { useState, useCallback } from 'react'
import { GEOLOGICAL_LAYER_KEYS, type GeologicalLayerKey, type GeologicalLayerVisibility } from '../../config/geologicalLayers'

const DEFAULT_VISIBILITY: GeologicalLayerVisibility = Object.fromEntries(
  GEOLOGICAL_LAYER_KEYS.map(k => [k, false])
) as GeologicalLayerVisibility

export function useGeologicalLayers() {
  const [geologicalLayers, setGeologicalLayers] = useState<GeologicalLayerVisibility>(DEFAULT_VISIBILITY)
  const [isLoadingGeological, setIsLoadingGeological] = useState<Partial<Record<GeologicalLayerKey, boolean>>>({})

  const toggleGeologicalLayer = useCallback((key: GeologicalLayerKey) => {
    setGeologicalLayers(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const hasVisibleGeologicalLayers = GEOLOGICAL_LAYER_KEYS.some(k => geologicalLayers[k])

  return {
    geologicalLayers,
    setGeologicalLayers,
    isLoadingGeological,
    setIsLoadingGeological,
    toggleGeologicalLayer,
    hasVisibleGeologicalLayers,
  }
}
