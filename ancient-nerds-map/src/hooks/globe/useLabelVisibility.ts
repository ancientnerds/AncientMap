/**
 * useLabelVisibility - Label type toggles and visibility state
 * Manages visibility for different label types (continents, oceans, etc.)
 */

import { useState, useCallback } from 'react'

export interface LabelTypesVisible {
  continent: boolean
  ocean: boolean
  country: boolean
  sea: boolean
  mountain: boolean
  desert: boolean
  capital: boolean
  lake: boolean
  river: boolean
  plate: boolean
  glacier: boolean
  coralReef: boolean
  leyLine: boolean
  tradeRoute: boolean
  [key: string]: boolean
}

interface LabelVisibilityOptions {
  initialGeoLabelsVisible?: boolean
  initialLabelTypesVisible?: Record<string, boolean>
  initialStarsVisible?: boolean
}

const DEFAULT_LABEL_TYPES: LabelTypesVisible = {
  continent: true,
  ocean: true,
  country: true,
  sea: true,
  mountain: true,
  desert: true,
  capital: true,
  lake: true,
  river: true,
  plate: true,
  glacier: true,
  coralReef: true,
  leyLine: true,
  tradeRoute: true
}

export function useLabelVisibility(options: LabelVisibilityOptions = {}) {
  const {
    initialGeoLabelsVisible = true,
    initialLabelTypesVisible = {},
    initialStarsVisible = true
  } = options

  // Main geo labels toggle
  const [geoLabelsVisible, setGeoLabelsVisible] = useState(initialGeoLabelsVisible)

  // Label types expanded state (for UI accordion)
  const [labelTypesExpanded, setLabelTypesExpanded] = useState(false)

  // Individual label type toggles
  const [labelTypesVisible, setLabelTypesVisible] = useState<LabelTypesVisible>({
    ...DEFAULT_LABEL_TYPES,
    ...initialLabelTypesVisible
  })

  // Stars visibility
  const [starsVisible, setStarsVisible] = useState(initialStarsVisible)

  // Toggle handlers
  const toggleGeoLabels = useCallback(() => {
    setGeoLabelsVisible(prev => !prev)
  }, [])

  const toggleLabelTypesExpanded = useCallback(() => {
    setLabelTypesExpanded(prev => !prev)
  }, [])

  const toggleLabelType = useCallback((type: string) => {
    setLabelTypesVisible(prev => ({ ...prev, [type]: !prev[type] }))
  }, [])

  const toggleStars = useCallback(() => {
    setStarsVisible(prev => !prev)
  }, [])

  return {
    // Main geo labels
    geoLabelsVisible,
    setGeoLabelsVisible,
    toggleGeoLabels,

    // Label types accordion
    labelTypesExpanded,
    setLabelTypesExpanded,
    toggleLabelTypesExpanded,

    // Individual label types
    labelTypesVisible,
    setLabelTypesVisible,
    toggleLabelType,

    // Stars
    starsVisible,
    setStarsVisible,
    toggleStars
  }
}
