/**
 * useStarsVisibility - Hook for managing stars visibility with fade animation
 *
 * Consolidates:
 * - Stars show/hide with fade animation
 */

import { useEffect } from 'react'
import * as THREE from 'three'
import type { GlobeRefs } from './types'

interface UseStarsVisibilityOptions {
  refs: GlobeRefs
  starsVisible: boolean
}

export function useStarsVisibility({
  refs,
  starsVisible,
}: UseStarsVisibilityOptions): void {
  // Handle stars visibility with fade animation
  useEffect(() => {
    const starsGroup = refs.stars.current
    const starPoints = starsGroup?.children[0] as THREE.Points | undefined
    if (!starsGroup || !starPoints) return

    const fm = refs.fadeManager.current

    if (starsVisible) {
      starsGroup.visible = true
      fm.fadeTo('stars', [starPoints.material as THREE.Material], 1)
    } else {
      fm.fadeTo('stars', [starPoints.material as THREE.Material], 0, {
        onComplete: () => { starsGroup.visible = false }
      })
    }
  }, [starsVisible, refs.stars, refs.fadeManager])
}
