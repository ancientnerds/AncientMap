/**
 * useFullscreen - Hook for managing fullscreen state
 *
 * Consolidates:
 * - Fullscreen toggle functionality
 * - Fullscreen state sync with browser API
 */

import { useEffect, useState, useCallback } from 'react'

interface UseFullscreenReturn {
  isFullscreen: boolean
  toggleFullscreen: () => void
}

export function useFullscreen(): UseFullscreenReturn {
  const [isFullscreen, setIsFullscreen] = useState(false)

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen()
    } else {
      document.exitFullscreen()
    }
  }, [])

  // Sync fullscreen state with actual fullscreen status
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }, [])

  return {
    isFullscreen,
    toggleFullscreen,
  }
}
