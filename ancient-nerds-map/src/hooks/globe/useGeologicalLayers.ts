/**
 * useGeologicalLayers - State management for geological overlay layers
 *
 * Manages:
 *   - visibility per layer key
 *   - loading state per layer key
 *   - current time-step index per layer key (used by temporal layers; ignored by static layers)
 */

import { useState, useCallback } from 'react'
import { GEOLOGICAL_LAYER_KEYS, type GeologicalLayerKey, type GeologicalLayerVisibility } from '../../config/geologicalLayers'

const DEFAULT_VISIBILITY: GeologicalLayerVisibility = Object.fromEntries(
  GEOLOGICAL_LAYER_KEYS.map(k => [k, false])
) as GeologicalLayerVisibility

const DEFAULT_TIME_STEP: Record<GeologicalLayerKey, number> = Object.fromEntries(
  GEOLOGICAL_LAYER_KEYS.map(k => [k, 0])
) as Record<GeologicalLayerKey, number>

export function useGeologicalLayers() {
  const [geologicalLayers, setGeologicalLayers] = useState<GeologicalLayerVisibility>(DEFAULT_VISIBILITY)
  const [isLoadingGeological, setIsLoadingGeological] = useState<Partial<Record<GeologicalLayerKey, boolean>>>({})
  const [currentTimeStep, setCurrentTimeStepState] =
    useState<Record<GeologicalLayerKey, number>>(DEFAULT_TIME_STEP)

  const toggleGeologicalLayer = useCallback((key: GeologicalLayerKey) => {
    setGeologicalLayers(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const setCurrentTimeStep = useCallback((key: GeologicalLayerKey, index: number) => {
    setCurrentTimeStepState(prev => (prev[key] === index ? prev : { ...prev, [key]: index }))
  }, [])

  const hasVisibleGeologicalLayers = GEOLOGICAL_LAYER_KEYS.some(k => geologicalLayers[k])

  return {
    geologicalLayers,
    setGeologicalLayers,
    isLoadingGeological,
    setIsLoadingGeological,
    toggleGeologicalLayer,
    hasVisibleGeologicalLayers,
    currentTimeStep,
    setCurrentTimeStep,
  }
}
