/**
 * Where the intro's camera starts and lands. initializeScene places the camera
 * with this at mount, and Globe moves the warp target with it while the warp
 * has not started (a geolocation that arrives after mount), so both must use
 * exactly the formula the scene always used.
 */

import { describe, expect, it } from 'vitest'

import { CAMERA } from '../../../../config/globeConstants'
import { computeWarpCameraPositions } from '../sceneInit'

/** The inline formula of sceneInit.ts before it became a function (commit 7df5e24). */
function legacy(initialPosition: [number, number] | null | undefined) {
  const startLng = initialPosition?.[0] ?? 10
  const startLat = initialPosition?.[1] ?? 51
  const startDist = CAMERA.MAX_DISTANCE
  const phi = (90 - startLat) * Math.PI / 180
  const theta = (startLng + 180) * Math.PI / 180
  const targetX = -startDist * Math.sin(phi) * Math.cos(theta)
  const targetY = startDist * Math.cos(phi)
  const targetZ = startDist * Math.sin(phi) * Math.sin(theta)
  return { start: [-targetX, targetY, -targetZ], target: [targetX, targetY, targetZ] }
}

describe('computeWarpCameraPositions', () => {
  it('defaults to 10 E / 51 N', () => {
    const { start, target } = computeWarpCameraPositions(null)
    expect(target.toArray()).toEqual(legacy([10, 51]).target)
    expect(start.toArray()).toEqual(legacy([10, 51]).start)
    expect(computeWarpCameraPositions(undefined).target.toArray()).toEqual(legacy([10, 51]).target)
  })

  it('keeps both points at the start distance, the start on the opposite side at the same latitude', () => {
    const { start, target } = computeWarpCameraPositions([-73.9, 40.7])
    expect(start.length()).toBeCloseTo(CAMERA.MAX_DISTANCE, 12)
    expect(target.length()).toBeCloseTo(CAMERA.MAX_DISTANCE, 12)
    expect(start.toArray()).toEqual([-target.x, target.y, -target.z])
  })

  it('equals the legacy inline formula', () => {
    for (const p of [[0, 0], [139.7, 35.7], [-58.4, -34.6], [180, 89.9], [-180, -90]] as [number, number][]) {
      const { start, target } = computeWarpCameraPositions(p)
      expect(start.toArray()).toEqual(legacy(p).start)
      expect(target.toArray()).toEqual(legacy(p).target)
    }
  })

  it('hands out fresh vectors every call (the loop mutates the camera, never these)', () => {
    const a = computeWarpCameraPositions([5, 5])
    const b = computeWarpCameraPositions([5, 5])
    expect(a.start).not.toBe(b.start)
    expect(a.target).not.toBe(b.target)
    expect(a.start).not.toBe(a.target)
  })
})
