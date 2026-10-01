/**
 * @vitest-environment jsdom
 *
 * Desktop camera motion, pinned.
 *
 * Touch gestures reuse the arcball rotation and the cursor-following zoom of
 * the mouse and wheel handlers (2026-10-01: the globe could not be turned or
 * zoomed with fingers). Those two pieces of maths are shared, not copied, so
 * they moved out of the handlers — and this file is what proves the desktop
 * did not notice. The numbers below were recorded from the handlers BEFORE the
 * move and must never change with it. Rounded to 10 decimals so a different
 * Node/V8 does not flake them; the move was additionally compared unrounded.
 */
import { describe, it, expect, vi } from 'vitest'
import { createArcballSystem, createMouseDownHandler, createMouseMoveHandler, createWheelHandler } from '../eventHandlers'
import { MIN_DIST, MAX_DIST, MAPBOX_SWITCH, mouseDrag as drag, position, round, scene, type Pose } from './cameraFixtures'

function wheel(pose: Pose, deltaY: number, x: number, y: number, controlsMin?: number) {
  const s = scene(pose, controlsMin)
  const { handleWheel } = createWheelHandler(
    s.camera, s.controls, s.globe, MIN_DIST, MAX_DIST,
    { current: false }, { current: 0 },
  )
  handleWheel({
    deltaY, clientX: x, clientY: y, currentTarget: s.canvas, preventDefault: () => {},
  } as unknown as WheelEvent)
  return s
}

const POSE: Pose = [10, 30, 2.0]

describe('wheel zoom (createWheelHandler)', () => {
  it('zooms in toward a point of the globe under the cursor', () => {
    expect(round(wheel(POSE, -100, 206, 457).camera.position)).toMatchInlineSnapshot(`
      [
        1.6544881585,
        0.9701350495,
        -0.2917309016,
      ]
    `)
    expect(round(wheel(POSE, -100, 100, 300).camera.position)).toMatchInlineSnapshot(`
      [
        1.6346850131,
        1.0134657676,
        -0.2535587621,
      ]
    `)
  })

  it('zooms out along the current direction', () => {
    expect(round(wheel(POSE, 100, 206, 457).camera.position)).toMatchInlineSnapshot(`
      [
        1.7569091758,
        1.03,
        -0.3097904904,
      ]
    `)
  })

  it('zooms in without steering when the cursor is off the globe', () => {
    const s = wheel([10, 30, 2.4], -100, 3, 3)
    expect(round(s.camera.position)).toMatchInlineSnapshot(`
      [
        1.9854779424,
        1.164,
        -0.3500933308,
      ]
    `)
    // same direction, shorter distance
    expect(s.camera.position.clone().normalize().distanceTo(position(10, 30, 1).normalize())).toBeLessThan(1e-12)
  })

  it('does nothing at the closest allowed distance and at the farthest', () => {
    expect(round(wheel([10, 30, MAPBOX_SWITCH], -100, 206, 457).camera.position)).toMatchInlineSnapshot(`
      [
        1.1121405657,
        0.652,
        -0.1961003881,
      ]
    `)
    expect(round(wheel([10, 30, MAX_DIST], 100, 206, 457).camera.position)).toMatchInlineSnapshot(`
      [
        2.080999218,
        1.22,
        -0.366936309,
      ]
    `)
  })

  it('zooms closer when the controls allow it (Mapbox ready)', () => {
    expect(round(wheel([10, 30, 1.3], -100, 206, 457, MIN_DIST).camera.position)).toMatchInlineSnapshot(`
      [
        1.075456551,
        0.6305187619,
        -0.1896320065,
      ]
    `)
  })

  it('updates the controls once per zoom step', () => {
    const s = wheel(POSE, -100, 206, 457)
    expect(s.controls.update).toHaveBeenCalledTimes(1)
    expect(s.controls.target.length()).toBe(0)
  })
})

describe('mouse drag rotation (createMouseDownHandler + createMouseMoveHandler)', () => {
  it('rotates the point under the cursor with it (arcball, on the globe)', () => {
    expect(drag(POSE, [[206, 457], [250, 470], [300, 400], [310, 380]]).after).toMatchInlineSnapshot(`
      [
        [
          1.7060022338,
          1.0267743188,
          -0.1878586609,
        ],
        [
          1.8015204757,
          0.8651976741,
          -0.0771813472,
        ],
        [
          1.8236375353,
          0.8193382745,
          -0.0550538976,
        ],
      ]
    `)
  })

  it('turns by screen-space rotation when the drag starts off the globe', () => {
    expect(drag([10, 30, 2.4], [[3, 3], [60, 40], [90, 120]]).after).toMatchInlineSnapshot(`
      [
        [
          1.8111516049,
          1.5618491911,
          0.200890439,
        ],
        [
          1.0341007492,
          2.1481793664,
          0.2756103232,
        ],
      ]
    `)
  })

  it('stops at the poles', () => {
    const path: Array<[number, number]> = [[206, 457]]
    for (let y = 440; y >= 5; y -= 15) path.push([206, y])
    const { after, camera } = drag(POSE, path)
    expect(after[after.length - 1]).toMatchInlineSnapshot(`
      [
        1.918105041,
        -0.454405727,
        -0.3382136706,
      ]
    `)
    expect(Math.abs(camera.position.clone().normalize().y)).toBeLessThan(0.996)
  })

  it('leaves the camera alone when the button is not down', () => {
    const s = scene(POSE)
    const before = round(s.camera.position)
    const { getArcballPoint } = createArcballSystem(s.camera, s.renderer)
    const { mouseState } = createMouseDownHandler({ current: false })
    const onMouseMove = createMouseMoveHandler(
      s.camera, s.renderer, s.controls, mouseState, getArcballPoint, { current: false },
      { current: { x: 0, y: 0 } }, { current: 0 }, { current: 0 }, { current: null },
      { current: false }, vi.fn(), vi.fn(), vi.fn(),
    )
    onMouseMove({ clientX: 250, clientY: 470 } as MouseEvent)
    expect(round(s.camera.position)).toEqual(before)
  })

  it('does nothing while Mapbox owns the mouse', () => {
    const s = scene(POSE)
    const before = round(s.camera.position)
    const showMapbox = { current: true }
    const { getArcballPoint } = createArcballSystem(s.camera, s.renderer)
    const { onMouseDown, mouseState } = createMouseDownHandler(showMapbox)
    const onMouseMove = createMouseMoveHandler(
      s.camera, s.renderer, s.controls, mouseState, getArcballPoint, showMapbox,
      { current: { x: 0, y: 0 } }, { current: 0 }, { current: 0 }, { current: null },
      { current: false }, vi.fn(), vi.fn(), vi.fn(),
    )
    onMouseDown({ button: 0, clientX: 206, clientY: 457 } as MouseEvent)
    onMouseMove({ clientX: 250, clientY: 470 } as MouseEvent)
    expect(round(s.camera.position)).toEqual(before)
  })
})
