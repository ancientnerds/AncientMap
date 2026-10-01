import { describe, it, expect } from 'vitest'
import * as THREE from 'three'
import { latLngAtScreen, latLngToCartesian } from '../geoMath'
import { zoomForSpan } from '../unifiedZoom'

/**
 * The finger hand-off from the Three.js globe to the Mapbox map keeps the scale:
 * two points of the globe that sat half a screen apart sit half a screen apart on
 * the map too. Until 2026-10-01 the hand-off converted the camera distance
 * linearly into a Mapbox zoom and the view jumped about five times closer (on a
 * phone, Europe became Milan).
 */
describe('zoomForSpan', () => {
  it('doubles the zoom scale per doubled distance', () => {
    expect(zoomForSpan(5, 100, 200)).toBeCloseTo(6, 12)
    expect(zoomForSpan(5, 200, 100)).toBeCloseTo(4, 12)
    expect(zoomForSpan(7.25, 300, 300)).toBe(7.25)
  })
})

describe('latLngAtScreen', () => {
  function cameraLookingAt(lat: number, lng: number, distance: number) {
    const camera = new THREE.PerspectiveCamera(60, 412 / 915, 0.01, 1500)
    camera.position.copy(latLngToCartesian(lat, lng, distance))
    camera.lookAt(0, 0, 0)
    camera.updateMatrixWorld()
    return camera
  }

  it('finds the point in the middle of the view', () => {
    const at = latLngAtScreen(cameraLookingAt(45, 10, 1.3), 0, 0)
    expect(at).not.toBeNull()
    expect(at!.lat).toBeCloseTo(45, 6)
    expect(at!.lng).toBeCloseTo(10, 6)
  })

  it('finds points left and right of the middle on the same parallel-ish line', () => {
    const camera = cameraLookingAt(0, 0, 1.3)
    const left = latLngAtScreen(camera, -0.5, 0)!
    const right = latLngAtScreen(camera, 0.5, 0)!
    expect(left.lng).toBeLessThan(0)
    expect(right.lng).toBeGreaterThan(0)
    expect(left.lng).toBeCloseTo(-right.lng, 9)
    expect(left.lat).toBeCloseTo(0, 9)
  })

  it('is null where the screen shows space', () => {
    expect(latLngAtScreen(cameraLookingAt(0, 0, 2.44), 0.99, 0.99)).toBeNull()
  })
})
