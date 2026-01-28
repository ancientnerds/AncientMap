/**
 * useContributePicker - Hook for managing contribute map picker mode
 *
 * Consolidates:
 * - Contribute picker hover detection (raycasting on globe)
 * - Show/hide coordinates when picker mode changes
 * - ESC key to cancel picker mode
 */

import { useEffect } from 'react'
import * as THREE from 'three'
import type { GlobeRefs } from './types'

interface UseContributePickerOptions {
  refs: GlobeRefs
  isActive?: boolean
  showCoordinates: boolean
  setShowCoordinates: (show: boolean) => void
  onHover?: (coords: [number, number] | null) => void
  onCancel?: () => void
}

export function useContributePicker({
  refs,
  isActive,
  showCoordinates,
  setShowCoordinates,
  onHover,
  onCancel,
}: UseContributePickerOptions): void {
  // Contribute map picker hover - raycasting on globe
  useEffect(() => {
    if (!refs.scene.current || !refs.container.current || !isActive) {
      return
    }

    const { globe, camera } = refs.scene.current
    const container = refs.container.current
    const raycaster = new THREE.Raycaster()

    const handleMouseMove = (e: MouseEvent) => {
      const mouseX = (e.clientX / window.innerWidth) * 2 - 1
      const mouseY = -(e.clientY / window.innerHeight) * 2 + 1

      raycaster.setFromCamera(new THREE.Vector2(mouseX, mouseY), camera)
      const hits = raycaster.intersectObject(globe, false)

      if (hits.length > 0) {
        const point = hits[0].point.normalize()
        const lat = 90 - Math.acos(point.y) * 180 / Math.PI
        const lng = Math.atan2(point.z, -point.x) * 180 / Math.PI - 180

        // Throttle to 50ms
        const now = performance.now()
        if (now - refs.contributeLastHoverTime.current >= 50) {
          onHover?.([lng, lat])
          refs.contributeLastHoverTime.current = now
        }
      } else {
        onHover?.(null)
      }
    }

    const handleMouseLeave = () => {
      onHover?.(null)
    }

    container.addEventListener('mousemove', handleMouseMove)
    container.addEventListener('mouseleave', handleMouseLeave)
    return () => {
      container.removeEventListener('mousemove', handleMouseMove)
      container.removeEventListener('mouseleave', handleMouseLeave)
    }
  }, [isActive, onHover, refs.scene, refs.container, refs.contributeLastHoverTime])

  // Manage showCoordinates when contribute picker is active
  useEffect(() => {
    if (isActive && !refs.wasContributePickerActive.current) {
      // Entering contribute picker - save current state and force on
      refs.showCoordsBeforeContribute.current = showCoordinates
      setShowCoordinates(true)
    } else if (!isActive && refs.wasContributePickerActive.current) {
      // Exiting contribute picker - restore original state
      setShowCoordinates(refs.showCoordsBeforeContribute.current)
    }
    refs.wasContributePickerActive.current = isActive ?? false
  }, [isActive, showCoordinates, setShowCoordinates, refs.wasContributePickerActive, refs.showCoordsBeforeContribute])

  // ESC key to cancel contribute picker
  useEffect(() => {
    if (!isActive) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onCancel) {
        onCancel()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isActive, onCancel])
}
