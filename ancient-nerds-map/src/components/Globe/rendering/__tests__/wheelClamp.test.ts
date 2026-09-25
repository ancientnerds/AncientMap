/**
 * The wheel handler clamps with controls.minDistance (the Mapbox switch
 * distance until Mapbox is ready). At the clamp a wheel-in must leave the
 * camera exactly where it is: steering toward the cursor first and letting
 * controls.update() snap the distance back would slide the globe sideways.
 */

import * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CAMERA, MAPBOX_SWITCH_DISTANCE } from '../../../../config/globeConstants'
import { createWheelHandler } from '../eventHandlers'

function scene(distance: number) {
  const camera = new THREE.PerspectiveCamera(13.2, 1, 0.01, 100)
  // Off-axis, so a float error in length() is realistic.
  camera.position.set(0.3, 0.5, 1).normalize().multiplyScalar(distance)
  camera.lookAt(0, 0, 0)
  camera.updateMatrixWorld()
  const controls = {
    minDistance: MAPBOX_SWITCH_DISTANCE,
    target: new THREE.Vector3(),
    update: vi.fn(),
  } as unknown as OrbitControls
  const globe = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 48))
  globe.updateMatrixWorld()
  const { handleWheel } = createWheelHandler(
    camera, controls, globe, CAMERA.MIN_DISTANCE, CAMERA.MAX_DISTANCE,
    { current: false }, { current: 60 },
  )
  // Cursor off-centre (but on the globe), so a steer would move the camera.
  const wheelIn = () => handleWheel({
    deltaY: -100,
    clientX: 60,
    clientY: 45,
    preventDefault: vi.fn(),
    currentTarget: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 100 }) },
  } as unknown as WheelEvent)
  return { camera, controls, wheelIn }
}

beforeEach(() => {
  vi.stubGlobal('window', { setTimeout, clearTimeout })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('wheel zoom at the orbit clamp', () => {
  it('leaves the camera unchanged at the switch distance', () => {
    const { camera, controls, wheelIn } = scene(MAPBOX_SWITCH_DISTANCE)
    const before = camera.position.clone()

    wheelIn()

    expect(camera.position.equals(before)).toBe(true)
    expect(controls.update).not.toHaveBeenCalled()
  })

  it('never takes the camera below controls.minDistance', () => {
    const { camera, wheelIn } = scene(MAPBOX_SWITCH_DISTANCE + 0.01)

    wheelIn()

    expect(camera.position.length()).toBeCloseTo(MAPBOX_SWITCH_DISTANCE, 9)
  })

  it('still zooms in above the clamp', () => {
    const { camera, controls, wheelIn } = scene(2)

    wheelIn()

    expect(camera.position.length()).toBeCloseTo(2 * 0.97, 9)
    expect(controls.update).toHaveBeenCalledOnce()
  })
})
