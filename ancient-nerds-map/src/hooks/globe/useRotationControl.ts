/**
 * useRotationControl - Hook for managing globe auto-rotation and play button state
 *
 * Consolidates:
 * - Play/pause toggle functionality
 * - Auto-pause when zoomed in or hovering list
 * - Manual rotation override
 * - Sync play button with actual rotation state
 */

import { useEffect, useState, useCallback } from 'react'
import type { GlobeRefs } from './types'

interface UseRotationControlOptions {
  refs: GlobeRefs
  isZoomedIn: boolean
  isHoveringList: boolean
}

interface UseRotationControlReturn {
  isPlaying: boolean
  toggle: () => void
  manualRotation: boolean
}

export function useRotationControl({
  refs,
  isZoomedIn,
  isHoveringList,
}: UseRotationControlOptions): UseRotationControlReturn {
  const [isPlaying, setIsPlaying] = useState(true)
  const [manualRotation, setManualRotation] = useState(false)

  // Toggle based on whether rotation is actually playing (not just enabled)
  const toggle = useCallback(() => {
    setIsPlaying(prev => {
      if (prev) {
        // Currently playing → stop
        refs.isAutoRotating.current = false
        refs.manualRotation.current = false
        setManualRotation(false)
        return false
      } else {
        // Currently stopped → start with manual override
        refs.isAutoRotating.current = true
        refs.manualRotation.current = true
        setManualRotation(true)
        return true
      }
    })
  }, [refs.isAutoRotating, refs.manualRotation])

  // Sync play button with actual rotation state (auto-pause when zoomed in or hovering, unless manual)
  useEffect(() => {
    const isPaused = isHoveringList || isZoomedIn

    // Clear manual override when user zooms out or stops hovering
    if (!isPaused && manualRotation) {
      setManualRotation(false)
      refs.manualRotation.current = false
    }

    const shouldAutoPause = isPaused && !manualRotation
    const actuallyRotating = refs.isAutoRotating.current && !shouldAutoPause

    // Also sync the ref for animation loop
    refs.manualRotation.current = manualRotation

    setIsPlaying(actuallyRotating)
  }, [isZoomedIn, isHoveringList, manualRotation, refs.isAutoRotating, refs.manualRotation])

  return {
    isPlaying,
    toggle,
    manualRotation,
  }
}
