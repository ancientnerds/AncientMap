/**
 * @vitest-environment jsdom
 *
 * Touch gestures on the globe.
 *
 * 2026-10-01, measured on production with a Pixel 7 emulation: one finger did
 * nothing, a pinch did nothing, and two fingers dragged the globe sideways out
 * of the middle (OrbitControls had rotate and zoom switched off but pan on).
 * Rotation and zoom are the mouse's own maths (cameraMotion.ts; the desktop is
 * pinned by desktopCameraMotion.test.ts). The tests here use the same
 * camera, sphere and canvas.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import * as THREE from 'three'
import { createArcballRotator } from '../cameraMotion'
import { createArcballSystem } from '../eventHandlers'
import { createTouchGestures } from '../touchGestures'
import { MIN_DIST, MAX_DIST, MAPBOX_SWITCH, mouseDrag, round, scene, type Pose } from './cameraFixtures'

const POSE: Pose = [10, 30, 2.0]

beforeEach(() => {
  vi.useFakeTimers({
    toFake: ['requestAnimationFrame', 'cancelAnimationFrame', 'performance', 'setTimeout', 'clearTimeout'],
  })
})
afterEach(() => {
  vi.useRealTimers()
})

type Kind = 'pointerdown' | 'pointermove' | 'pointerup' | 'pointercancel'

function ev(type: Kind, id: number, x: number, y: number, pointerType = 'touch'): PointerEvent {
  return { type, pointerType, pointerId: id, clientX: x, clientY: y } as unknown as PointerEvent
}

function harness(pose: Pose = POSE) {
  const s = scene(pose)
  const showMapbox = { current: false }
  const { getArcballPoint } = createArcballSystem(s.camera, s.renderer)
  const rotate = createArcballRotator(s.camera, s.controls, getArcballPoint)
  const g = createTouchGestures({
    canvas: s.canvas,
    camera: s.camera,
    controls: s.controls,
    globe: s.globe,
    minDist: MIN_DIST,
    maxDist: MAX_DIST,
    showMapboxRef: showMapbox,
    rotate,
  })
  const send = (e: PointerEvent) => {
    if (e.type === 'pointerdown') g.onPointerDown(e)
    else if (e.type === 'pointermove') g.onPointerMove(e)
    else g.onPointerEnd(e)
  }
  const dist = () => s.camera.position.length()
  const dir = () => s.camera.position.clone().normalize()
  /** One rendered frame: pending frame callbacks run, then three refreshes the camera matrix. */
  const frame = () => {
    vi.advanceTimersByTime(16)
    s.camera.updateMatrixWorld()
  }
  return { ...s, g, send, showMapbox, dist, dir, frame }
}

/** A point on the unit sphere in the direction of a lng/lat. */
function surfacePoint(lng: number, lat: number): THREE.Vector3 {
  const latR = (lat * Math.PI) / 180
  const theta = ((lng + 180) * Math.PI) / 180
  return new THREE.Vector3(-Math.cos(latR) * Math.cos(theta), Math.sin(latR), Math.cos(latR) * Math.sin(theta))
}

/** The pixel at which the camera sees a point of the sphere. */
function pixelOf(h: ReturnType<typeof harness>, p: THREE.Vector3): [number, number] {
  const v = p.clone().project(h.camera)
  return [((v.x + 1) / 2) * 412, ((1 - v.y) / 2) * 915]
}

describe('one finger', () => {
  it('turns the globe exactly as the same mouse drag does', () => {
    const path: Array<[number, number]> = [[206, 457], [250, 470], [300, 400], [310, 380]]
    const h = harness()
    h.send(ev('pointerdown', 1, ...path[0]))
    const after = path.slice(1).map(([x, y]) => {
      h.send(ev('pointermove', 1, x, y))
      return round(h.camera.position)
    })
    expect(after).toEqual(mouseDrag(POSE, path).after)
  })

  it('keeps the grabbed point of the globe under the finger', () => {
    const h = harness()
    const grabbed = surfacePoint(10, 30) // the point in the middle of the view at POSE
    const [x0, y0] = pixelOf(h, grabbed)
    h.send(ev('pointerdown', 1, x0, y0))
    for (let i = 1; i <= 6; i++) {
      h.send(ev('pointermove', 1, x0 + i * 10, y0 - i * 5))
      h.frame()
    }
    const [x1, y1] = pixelOf(h, grabbed)
    // Within a few pixels of where the finger is (the arcball keeps the roll
    // level, so it is close, not exact).
    expect(Math.hypot(x1 - (x0 + 60), y1 - (y0 - 30))).toBeLessThan(8)
  })

  it('does not zoom, pan or leave the unit sphere around the origin', () => {
    const h = harness()
    const d0 = h.dist()
    h.send(ev('pointerdown', 1, 206, 457))
    h.send(ev('pointermove', 1, 300, 380))
    expect(h.dist()).toBeCloseTo(d0, 12)
    expect(h.controls.target.length()).toBe(0)
  })
})

describe('pointers that are not fingers', () => {
  it.each(['mouse', 'pen'])('ignores a %s pointer (the mouse handlers own it)', type => {
    const h = harness()
    const before = round(h.camera.position)
    h.send(ev('pointerdown', 1, 206, 457, type))
    h.send(ev('pointermove', 1, 300, 380, type))
    h.send(ev('pointerup', 1, 300, 380, type))
    expect(round(h.camera.position)).toEqual(before)
  })
})

describe('two fingers: pinch', () => {
  /** Two fingers placed `gap` px apart, centred at (cx, cy), then moved to `to` px apart. */
  function pinch(h: ReturnType<typeof harness>, cx: number, cy: number, from: number, to: number, steps = 6) {
    h.send(ev('pointerdown', 1, cx - from / 2, cy))
    h.send(ev('pointerdown', 2, cx + from / 2, cy))
    for (let i = 1; i <= steps; i++) {
      const gap = from + ((to - from) * i) / steps
      h.send(ev('pointermove', 1, cx - gap / 2, cy))
      h.send(ev('pointermove', 2, cx + gap / 2, cy))
      h.frame()
    }
  }

  it('spreading zooms in, pinching together zooms out', () => {
    const inH = harness([10, 30, 2.0])
    pinch(inH, 206, 457.5, 80, 240)
    expect(inH.dist()).toBeLessThan(2.0)

    const outH = harness([10, 30, 1.6])
    pinch(outH, 206, 457.5, 240, 80)
    expect(outH.dist()).toBeGreaterThan(1.6)
  })

  it('zooms by the ratio of the finger distance, not by how often the fingers moved', () => {
    // 80 -> 110 px is a ratio of 1.375: from distance 2.0 the camera ends at
    // 2.0 / 1.375, well inside the clamp, however finely the spread is sampled.
    const coarse = harness()
    pinch(coarse, 206, 457.5, 80, 110, 2)
    const fine = harness()
    pinch(fine, 206, 457.5, 80, 110, 20)
    expect(coarse.dist()).toBeCloseTo((2.0 * 80) / 110, 6)
    expect(fine.dist()).toBeCloseTo((2.0 * 80) / 110, 6)
  })

  it('stops at the closest distance the controls allow, and at the farthest', () => {
    const closeH = harness([10, 30, 1.4])
    pinch(closeH, 206, 457.5, 40, 400)
    expect(closeH.dist()).toBeGreaterThanOrEqual(MAPBOX_SWITCH - 1e-9)

    const farH = harness([10, 30, 2.3])
    pinch(farH, 206, 457.5, 400, 40)
    expect(farH.dist()).toBeLessThanOrEqual(MAX_DIST + 1e-9)
  })

  it('leans toward the point between the fingers, as the wheel leans toward the cursor', () => {
    const centred = harness()
    pinch(centred, 206, 457.5, 80, 200)
    const offCentre = harness()
    pinch(offCentre, 90, 250, 80, 200)

    // The point of the globe under the off-centre fingers before the gesture
    const probe = harness()
    const target = probe.dir().clone() // placeholder, replaced below
    const ndc = new THREE.Vector2((90 / 412) * 2 - 1, -(250 / 915) * 2 + 1)
    const ray = new THREE.Raycaster()
    ray.setFromCamera(ndc, probe.camera)
    const hit = ray.intersectObject(probe.globe, false)[0].point.normalize()
    target.copy(hit)

    expect(offCentre.dir().angleTo(target)).toBeLessThan(centred.dir().angleTo(target))
  })

  it('does not turn the globe', () => {
    const h = harness()
    const dir0 = h.dir()
    pinch(h, 206, 457.5, 80, 200)
    // a centred pinch changes the distance only
    expect(h.dir().angleTo(dir0)).toBeLessThan(1e-9)
  })
})

describe('two fingers: dragging both together', () => {
  it('neither zooms, turns nor pans the globe', () => {
    const h = harness()
    const before = round(h.camera.position)
    h.send(ev('pointerdown', 1, 166, 457))
    h.send(ev('pointerdown', 2, 246, 457))
    // A browser reports the two fingers one pointermove at a time, so between
    // the two reports of a step the finger distance is momentarily off.
    for (let i = 1; i <= 8; i++) {
      h.send(ev('pointermove', 1, 166 + i * 10, 457))
      h.send(ev('pointermove', 2, 246 + i * 10, 457))
      h.frame()
    }
    expect(round(h.camera.position)).toEqual(before)
    expect(h.controls.target.length()).toBe(0)
  })
})

describe('changing the number of fingers', () => {
  it('goes on turning from where the remaining finger is, without a jump', () => {
    const h = harness()
    h.send(ev('pointerdown', 1, 150, 457))
    h.send(ev('pointerdown', 2, 260, 457))
    h.send(ev('pointermove', 1, 140, 457))
    h.send(ev('pointermove', 2, 270, 457))
    h.frame()
    h.send(ev('pointerup', 1, 140, 457))
    const afterLift = round(h.camera.position)
    h.frame()

    // Next move of finger 2 by 3px: a 3px turn, not a swing from finger 1's place.
    h.send(ev('pointermove', 2, 273, 457))
    const moved = h.camera.position.clone().normalize()
    const reference = harness()
    reference.camera.position.fromArray(afterLift)
    reference.camera.lookAt(0, 0, 0)
    reference.camera.updateMatrixWorld()
    const { getArcballPoint } = createArcballSystem(reference.camera, reference.renderer)
    createArcballRotator(reference.camera, reference.controls, getArcballPoint)({ x: 270, y: 457 }, { x: 273, y: 457 })
    expect(moved.angleTo(reference.camera.position.clone().normalize())).toBeLessThan(1e-9)
  })

  it('treats a lone second finger after the first lifted like a first finger', () => {
    const h = harness()
    const before = round(h.camera.position)
    h.send(ev('pointerdown', 1, 150, 457))
    h.send(ev('pointerup', 1, 150, 457))
    h.send(ev('pointerdown', 2, 200, 457))
    expect(round(h.camera.position)).toEqual(before)
  })
})

describe('while Mapbox shows the map', () => {
  it('leaves the gesture to Mapbox', () => {
    const h = harness()
    h.showMapbox.current = true
    const before = round(h.camera.position)
    h.send(ev('pointerdown', 1, 206, 457))
    h.send(ev('pointermove', 1, 300, 380))
    h.send(ev('pointerdown', 2, 100, 100))
    h.send(ev('pointermove', 2, 40, 40))
    expect(round(h.camera.position)).toEqual(before)
  })
})

describe('inertia after a flick', () => {
  /** A finger that sweeps 10px per 16ms and lifts right away. */
  function flick(h: ReturnType<typeof harness>, liftAfterMs = 0) {
    h.send(ev('pointerdown', 1, 150, 457))
    for (let i = 1; i <= 6; i++) {
      vi.advanceTimersByTime(16)
      h.send(ev('pointermove', 1, 150 + i * 10, 457))
    }
    vi.advanceTimersByTime(liftAfterMs)
    h.send(ev('pointerup', 1, 210, 457))
  }

  it('keeps the globe turning after the finger lifts, then comes to rest by itself', () => {
    const h = harness()
    flick(h)
    const atLift = round(h.camera.position)

    vi.advanceTimersByTime(48)
    const soonAfter = round(h.camera.position)
    expect(soonAfter).not.toEqual(atLift)

    vi.advanceTimersByTime(5000)
    const settled = round(h.camera.position)
    vi.advanceTimersByTime(1000)
    expect(round(h.camera.position)).toEqual(settled)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('turns the same way the finger was moving', () => {
    const h = harness()
    const lng = () => (Math.atan2(h.camera.position.z, -h.camera.position.x) * 180) / Math.PI
    // signed turn from a to b in degrees, across the +-180 seam
    const turn = (a: number, b: number) => ((((b - a) % 360) + 540) % 360) - 180
    const before = lng()
    flick(h)
    const atLift = lng()
    vi.advanceTimersByTime(2000)
    const after = lng()
    // dragging right turned the camera one way; the glide continues that way
    expect(turn(before, atLift)).not.toBe(0)
    expect(Math.sign(turn(atLift, after))).toBe(Math.sign(turn(before, atLift)))
    expect(Math.abs(turn(atLift, after))).toBeGreaterThan(1)
  })

  it('has no inertia when the finger rested before lifting', () => {
    const h = harness()
    flick(h, 250)
    const atLift = round(h.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(h.camera.position)).toEqual(atLift)
  })

  it('has no inertia after a slow drag', () => {
    const h = harness()
    h.send(ev('pointerdown', 1, 150, 457))
    for (let i = 1; i <= 6; i++) {
      vi.advanceTimersByTime(100)
      h.send(ev('pointermove', 1, 150 + i, 457))
    }
    h.send(ev('pointerup', 1, 156, 457))
    const atLift = round(h.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(h.camera.position)).toEqual(atLift)
  })

  it('has no inertia after pointercancel', () => {
    const h = harness()
    h.send(ev('pointerdown', 1, 150, 457))
    for (let i = 1; i <= 6; i++) {
      vi.advanceTimersByTime(16)
      h.send(ev('pointermove', 1, 150 + i * 10, 457))
    }
    h.send(ev('pointercancel', 1, 210, 457))
    const atCancel = round(h.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(h.camera.position)).toEqual(atCancel)
  })

  it('has no inertia after a pinch', () => {
    const h = harness()
    h.send(ev('pointerdown', 1, 150, 457))
    h.send(ev('pointerdown', 2, 260, 457))
    for (let i = 1; i <= 6; i++) {
      vi.advanceTimersByTime(16)
      h.send(ev('pointermove', 1, 150 - i * 10, 457))
      h.send(ev('pointermove', 2, 260 + i * 10, 457))
    }
    h.send(ev('pointerup', 2, 320, 457))
    h.send(ev('pointerup', 1, 90, 457))
    const atLift = round(h.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(h.camera.position)).toEqual(atLift)
  })

  it('stops the moment a new finger touches down', () => {
    const h = harness()
    flick(h)
    vi.advanceTimersByTime(32)
    h.send(ev('pointerdown', 2, 100, 600))
    const held = round(h.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(h.camera.position)).toEqual(held)
  })

  it('stops when Mapbox takes over', () => {
    const h = harness()
    flick(h)
    vi.advanceTimersByTime(32)
    h.showMapbox.current = true
    const held = round(h.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(h.camera.position)).toEqual(held)
  })

  it('dispose stops a glide in progress', () => {
    const h = harness()
    flick(h)
    vi.advanceTimersByTime(32)
    h.g.dispose()
    const held = round(h.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(h.camera.position)).toEqual(held)
    expect(vi.getTimerCount()).toBe(0)
  })
})
