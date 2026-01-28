/**
 * usePaleoshoreline - Sea level visualization state
 * Manages paleoshoreline visibility and sea level controls
 */

import { useState, useCallback } from 'react'

interface PaleoshorelineOptions {
  initialSeaLevel?: number
  initialVisible?: boolean
  initialReplaceCoastlines?: boolean
}

export function usePaleoshoreline(options: PaleoshorelineOptions = {}) {
  const {
    initialSeaLevel = -120, // Default to LGM (Last Glacial Maximum)
    initialVisible = false,
    initialReplaceCoastlines = false
  } = options

  // Visibility
  const [paleoshorelineVisible, setPaleoshorelineVisible] = useState(initialVisible)

  // Sea level (actual committed value)
  const [seaLevel, setSeaLevel] = useState(initialSeaLevel)

  // Slider sea level (for smooth UI during drag)
  const [sliderSeaLevel, setSliderSeaLevel] = useState(initialSeaLevel)

  // Loading state
  const [isLoadingPaleoshoreline, setIsLoadingPaleoshoreline] = useState(false)

  // Replace coastlines toggle
  const [replaceCoastlines, setReplaceCoastlines] = useState(initialReplaceCoastlines)

  // Toggle visibility
  const togglePaleoshoreline = useCallback(() => {
    setPaleoshorelineVisible(prev => !prev)
  }, [])

  // Set sea level and sync slider
  const setSeaLevelWithSlider = useCallback((level: number) => {
    const clamped = Math.max(-150, Math.min(-1, level))
    setSeaLevel(clamped)
    setSliderSeaLevel(clamped)
  }, [])

  // Preset buttons
  const setLGM = useCallback(() => {
    setSeaLevelWithSlider(-120)
  }, [setSeaLevelWithSlider])

  const setNearPresent = useCallback(() => {
    setSeaLevelWithSlider(-1)
  }, [setSeaLevelWithSlider])

  return {
    // Visibility
    paleoshorelineVisible,
    setPaleoshorelineVisible,
    togglePaleoshoreline,

    // Sea level
    seaLevel,
    setSeaLevel,
    sliderSeaLevel,
    setSliderSeaLevel,
    setSeaLevelWithSlider,

    // Presets
    setLGM,
    setNearPresent,

    // Loading
    isLoadingPaleoshoreline,
    setIsLoadingPaleoshoreline,

    // Replace coastlines
    replaceCoastlines,
    setReplaceCoastlines
  }
}
