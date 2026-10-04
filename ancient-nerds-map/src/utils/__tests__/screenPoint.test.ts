/**
 * window.__DEMO.screenPoint: where the page draws a place, for the studio's
 * globe pins and the platform take's measure clicks.
 */
import * as THREE from 'three'
import { describe, expect, it } from 'vitest'

import { latLngToPosition } from '../geoUtils'
import { globeScreenPoint, viewportPoint } from '../screenPoint'

function cameraAbove(lat: number, lng: number, distance: number, fov = 60): THREE.PerspectiveCamera {
  const camera = new THREE.PerspectiveCamera(fov, 1920 / 1080, 0.01, 1500)
  camera.position.copy(latLngToPosition(lng, lat, distance))
  camera.lookAt(0, 0, 0)
  camera.updateMatrixWorld()
  camera.updateProjectionMatrix()
  return camera
}

describe('globeScreenPoint', () => {
  it('puts the point under the camera at the viewport centre', () => {
    const p = globeScreenPoint(cameraAbove(34, 36.2, 1.8), 34, 36.2, 1920, 1080)
    expect(p?.x).toBeCloseTo(960, 3)
    expect(p?.y).toBeCloseTo(540, 3)
  })
  it('puts points east to the right and north up', () => {
    const camera = cameraAbove(0, 0, 2)
    const east = globeScreenPoint(camera, 0, 10, 1920, 1080)
    const north = globeScreenPoint(camera, 10, 0, 1920, 1080)
    expect(east && east.x > 960).toBe(true)
    expect(north && north.y < 540).toBe(true)
  })
  it('narrows with the telephoto FOV: the same place lies further from the centre', () => {
    const wide = globeScreenPoint(cameraAbove(34, 36.2, 1.35, 60), 33, 36.2, 1920, 1080)
    const tele = globeScreenPoint(cameraAbove(34, 36.2, 1.35, 15.1), 33, 36.2, 1920, 1080)
    expect(wide && tele && tele.y - 540 > 3 * (wide.y - 540)).toBe(true)
  })
  it('hides the far side of the globe and points outside the viewport', () => {
    expect(globeScreenPoint(cameraAbove(0, 0, 2), 0, 180, 1920, 1080)).toBeNull()
    expect(globeScreenPoint(cameraAbove(34, 36.2, 1.35, 15.1), 10, 36.2, 1920, 1080)).toBeNull()
  })
})

describe('viewportPoint', () => {
  it('keeps points inside the viewport only', () => {
    expect(viewportPoint({ x: 10, y: 20 }, 1920, 1080)).toEqual({ x: 10, y: 20 })
    expect(viewportPoint({ x: -1, y: 20 }, 1920, 1080)).toBeNull()
    expect(viewportPoint({ x: 10, y: 1081 }, 1920, 1080)).toBeNull()
  })
})
