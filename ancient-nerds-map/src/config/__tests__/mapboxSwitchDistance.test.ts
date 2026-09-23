/**
 * The Mapbox switch point in camera distance. The zoom state switches to
 * Mapbox at TRANSITION_POINT 66, which is scaledZoom THREEJS_CAMERA_MAX (80 %)
 * of the camera range: 2.44 − 0.8 × 1.42 = 1.304. Until Mapbox is ready the
 * orbit controls may not come closer than that, so nobody sees the Three.js
 * globe at a zoom it never showed before.
 */

import { describe, expect, it } from 'vitest'

import { CAMERA, MAPBOX_SWITCH_DISTANCE, THREEJS_CAMERA_MAX, orbitMinDistance } from '../globeConstants'

/** The animation loop's zoom-state formula (animationLoop.ts, eventHandlers.ts). */
function loopZoom(cameraDist: number): number {
  const scaledZoom = ((CAMERA.MAX_DISTANCE - cameraDist) / (CAMERA.MAX_DISTANCE - CAMERA.MIN_DISTANCE)) * 100
  return Math.round(Math.max(0, Math.min(66, (scaledZoom / THREEJS_CAMERA_MAX) * 66)))
}

describe('MAPBOX_SWITCH_DISTANCE', () => {
  it('is 2.44 − 0.8 × 1.42 = 1.304', () => {
    expect(THREEJS_CAMERA_MAX).toBe(80)
    expect(MAPBOX_SWITCH_DISTANCE).toBeCloseTo(1.304, 10)
  })

  it('maps to zoom state 66 in the loop formula, and 1.3127 still maps to 65', () => {
    expect(loopZoom(MAPBOX_SWITCH_DISTANCE)).toBe(66)
    expect(loopZoom(1.3127)).toBe(65)
  })
})

describe('orbitMinDistance', () => {
  it('holds the camera at the switch distance until Mapbox is ready or has failed', () => {
    expect(orbitMinDistance('idle')).toBe(MAPBOX_SWITCH_DISTANCE)
    expect(orbitMinDistance('loading')).toBe(MAPBOX_SWITCH_DISTANCE)
    expect(orbitMinDistance('ready')).toBe(CAMERA.MIN_DISTANCE)
    expect(orbitMinDistance('failed')).toBe(CAMERA.MIN_DISTANCE)
  })
})
