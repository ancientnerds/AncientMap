/**
 * useTooltipHandlers - Hook for managing tooltip mouse interactions
 *
 * Consolidates:
 * - Tooltip mouse enter/leave handlers
 * - Frozen state management
 */

import { useCallback } from 'react'
import type { GlobeRefs } from './types'

interface UseTooltipHandlersOptions {
  refs: GlobeRefs
  setIsFrozen: (frozen: boolean) => void
  setFrozenSite: (site: null) => void
}

interface UseTooltipHandlersReturn {
  handleTooltipMouseEnter: () => void
  handleTooltipMouseLeave: () => void
}

export function useTooltipHandlers({
  refs,
  setIsFrozen,
  setFrozenSite,
}: UseTooltipHandlersOptions): UseTooltipHandlersReturn {
  const handleTooltipMouseEnter = useCallback(() => {
    refs.isHoveringTooltip.current = true
    refs.lastMousePos.current = { x: -1000, y: -1000 }
  }, [refs.isHoveringTooltip, refs.lastMousePos])

  const handleTooltipMouseLeave = useCallback(() => {
    refs.isHoveringTooltip.current = false
    // 200ms grace period, then unfreeze
    setTimeout(() => {
      if (!refs.isHoveringTooltip.current) {
        refs.isFrozen.current = false
        setIsFrozen(false)
        setFrozenSite(null)
        refs.sitesPassedDuringFreeze.current = 0
      }
    }, 200)
  }, [refs.isHoveringTooltip, refs.isFrozen, refs.sitesPassedDuringFreeze, setIsFrozen, setFrozenSite])

  return {
    handleTooltipMouseEnter,
    handleTooltipMouseLeave,
  }
}
