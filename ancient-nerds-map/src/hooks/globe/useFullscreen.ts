/**
 * useFullscreen - Hook for managing fullscreen state
 *
 * Consolidates:
 * - Fullscreen toggle functionality
 * - Fullscreen state sync with browser API
 *
 * canFullscreen exists because the Fullscreen API is not universal: iOS Safari
 * has no Element.requestFullscreen at all. The globe's fullscreen button threw
 * "document.documentElement.requestFullscreen is not a function" there on two
 * sessions 2026-09-27..30 (page=globe, iOS). The other two call sites in this
 * codebase already guard it - SitePopup.tsx wraps the call in try/catch,
 * WebcamStreamOverlay.tsx uses `el.requestFullscreen?.()`. This hook was the one
 * that did not, and a button that can only throw is worse than no button: the
 * caller hides it (ZoomControls) rather than offering a dead control.
 */

import { useEffect, useState, useCallback } from 'react'

interface UseFullscreenReturn {
  isFullscreen: boolean
  canFullscreen: boolean
  toggleFullscreen: () => void
}

export function useFullscreen(): UseFullscreenReturn {
  const [isFullscreen, setIsFullscreen] = useState(false)
  // Read once during the first render, on both sides: this is a capability of
  // the browser, not of the visitor, so it cannot differ between server and
  // client and needs no effect to settle.
  const [canFullscreen] = useState(
    () =>
      typeof document !== 'undefined' &&
      typeof document.documentElement.requestFullscreen === 'function',
  )

  const toggleFullscreen = useCallback(() => {
    if (!canFullscreen) return
    if (!document.fullscreenElement) {
      void document.documentElement.requestFullscreen()
    } else {
      void document.exitFullscreen()
    }
  }, [canFullscreen])

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
    canFullscreen,
    toggleFullscreen,
  }
}
