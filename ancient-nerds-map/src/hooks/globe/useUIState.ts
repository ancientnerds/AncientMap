/**
 * useUIState - HUD visibility, scale, tooltips, coordinates state management
 * Manages all UI state for the Globe component
 */

import { useState, useEffect, useCallback } from 'react'

interface UIStateOptions {
  initialHudScale?: number
  initialDotSize?: number
  initialShowTooltips?: boolean
  initialShowCoordinates?: boolean
  initialShowScale?: boolean
}

export function useUIState(options: UIStateOptions = {}) {
  const {
    initialHudScale = 0.9,
    initialDotSize = 6,
    initialShowTooltips = true,
    initialShowCoordinates = false,
    initialShowScale = true
  } = options

  // HUD visibility
  const [hudVisible, setHudVisible] = useState(true)

  // HUD scale (50% to 130%)
  const [hudScale, setHudScale] = useState(initialHudScale)
  const [hudScalePreview, setHudScalePreview] = useState<number | null>(null)

  // Dot size (1 to 15)
  const [dotSize, setDotSize] = useState(initialDotSize)

  // Display toggles
  const [showTooltips, setShowTooltips] = useState(initialShowTooltips)
  const [showCoordinates, setShowCoordinates] = useState(initialShowCoordinates)
  const [showScale, setShowScale] = useState(initialShowScale)

  // Apply HUD scale as global CSS variable
  useEffect(() => {
    document.documentElement.style.setProperty('--hud-scale', String(hudScale))
  }, [hudScale])

  // Toggle body class for HUD visibility
  useEffect(() => {
    if (hudVisible) {
      document.body.classList.remove('hud-hidden')
    } else {
      document.body.classList.add('hud-hidden')
    }
  }, [hudVisible])

  // Toggle handlers
  const toggleTooltips = useCallback(() => {
    setShowTooltips(prev => !prev)
  }, [])

  const toggleCoordinates = useCallback(() => {
    setShowCoordinates(prev => !prev)
  }, [])

  const toggleScale = useCallback(() => {
    setShowScale(prev => !prev)
  }, [])

  const hideHud = useCallback(() => {
    setHudVisible(false)
  }, [])

  const showHud = useCallback(() => {
    setHudVisible(true)
  }, [])

  return {
    // HUD visibility
    hudVisible,
    setHudVisible,
    hideHud,
    showHud,

    // HUD scale
    hudScale,
    setHudScale,
    hudScalePreview,
    setHudScalePreview,

    // Dot size
    dotSize,
    setDotSize,

    // Display toggles
    showTooltips,
    setShowTooltips,
    toggleTooltips,
    showCoordinates,
    setShowCoordinates,
    toggleCoordinates,
    showScale,
    setShowScale,
    toggleScale
  }
}
