/**
 * useFlyToAnimation - Hook for managing fly-to camera animation
 *
 * Consolidates:
 * - Fly-to effect (rotate to coordinates from search results)
 * - Camera animation with spherical interpolation (slerp)
 * - Mapbox mode fly-to support
 */

import { useEffect } from 'react'
import * as THREE from 'three'
import type { GlobeRefs } from './types'

interface UseFlyToAnimationOptions {
  refs: GlobeRefs
  flyTo?: [number, number] | null  // [lng, lat] coordinates to fly to
}

export function useFlyToAnimation({
  refs,
  flyTo,
}: UseFlyToAnimationOptions): void {
  // Rotate to coordinates when flyTo prop changes (search result) - no zoom
  useEffect(() => {
    if (!flyTo) return

    const [lng, lat] = flyTo

    // Handle Mapbox mode
    if (refs.showMapbox.current && refs.mapboxService.current?.getIsInitialized()) {
      refs.mapboxService.current.flyTo(lat, lng, 600)
      return
    }

    // Handle Three.js globe mode
    if (!refs.scene.current) return

    const { camera, controls } = refs.scene.current

    // Keep current distance (no zoom change)
    const currentDist = camera.position.length()

    // Convert lat/lng to unit vector direction (target direction)
    const phi = (90 - lat) * Math.PI / 180
    const theta = (lng + 180) * Math.PI / 180
    const targetDir = new THREE.Vector3(
      -Math.sin(phi) * Math.cos(theta),
      Math.cos(phi),
      Math.sin(phi) * Math.sin(theta)
    ).normalize()

    // Get start direction (normalized current position)
    const startDir = camera.position.clone().normalize()

    // Cancel any existing camera animation
    if (refs.cameraAnimation.current) {
      cancelAnimationFrame(refs.cameraAnimation.current)
      refs.cameraAnimation.current = null
    }

    // Pause auto-rotation during animation
    const wasRotating = refs.isAutoRotating.current
    refs.isAutoRotating.current = false

    // Animate using spherical interpolation (slerp) to avoid diving through globe
    const duration = 600 // ms
    const startTime = performance.now()

    // Use quaternions for proper spherical interpolation
    const startQuat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), startDir)
    const targetQuat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), targetDir)
    const currentQuat = new THREE.Quaternion()

    const animateRotate = () => {
      const elapsed = performance.now() - startTime
      const progress = Math.min(1, elapsed / duration)
      const eased = 1 - Math.pow(1 - progress, 3) // Ease out cubic

      // Spherical interpolation of direction
      currentQuat.slerpQuaternions(startQuat, targetQuat, eased)
      const currentDir = new THREE.Vector3(0, 0, 1).applyQuaternion(currentQuat)

      // Apply fixed distance to get camera position (maintains zoom level)
      camera.position.copy(currentDir.multiplyScalar(currentDist))
      camera.lookAt(0, 0, 0)
      controls.update()

      if (progress < 1) {
        refs.cameraAnimation.current = requestAnimationFrame(animateRotate)
      } else {
        refs.cameraAnimation.current = null
        // Resume rotation after animation if it was rotating before
        if (wasRotating) {
          refs.isAutoRotating.current = true
        }
      }
    }

    refs.cameraAnimation.current = requestAnimationFrame(animateRotate)
  }, [flyTo, refs.showMapbox, refs.mapboxService, refs.scene, refs.cameraAnimation, refs.isAutoRotating])
}
