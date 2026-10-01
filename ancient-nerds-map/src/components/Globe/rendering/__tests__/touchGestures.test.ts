/**
 * @vitest-environment jsdom
 *
 * Touch gestures on the globe and the map.
 *
 * 2026-10-01, morning (Pixel 7 emulation on production): one finger did
 * nothing, a pinch did nothing, two fingers dragged the globe out of the
 * middle. Afternoon, the owner on his phone: a pinch did not zoom like the
 * double tap, and after it he could not zoom out with two fingers. Measured:
 * at 66 % the pinch handed over to the Mapbox map with a fivefold jump and
 * then died, and a pinch on the map never moved the slider, so the 3D globe
 * never came back.
 *
 * The gestures are read on the element both map layers sit in, so one
 * gesture lives on across a switch between the Three.js globe and the Mapbox
 * map, in both directions. Rotation and zoom on the globe are the mouse's own
 * maths (cameraMotion.ts; the desktop is pinned by desktopCameraMotion.test.ts).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import * as THREE from 'three'
import { createArcballRotator, screenOf } from '../cameraMotion'
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

function harness(pose: Pose = POSE, controlsMinDistance = MAPBOX_SWITCH) {
  const s = scene(pose, controlsMinDistance)
  const showMapbox = { current: false }
  const { getArcballPoint } = createArcballSystem(s.camera, s.renderer)
  const rotate = createArcballRotator(s.camera, s.controls, getArcballPoint)
  const threeLayer = document.createElement('div')
  const mapboxLayer = document.createElement('div')
  const panel = document.createElement('div')
  const mapbox = { zoomAround: vi.fn() }
  const touchGestureActive = { current: false }
  const g = createTouchGestures({
    mapLayers: [threeLayer, mapboxLayer],
    canvas: s.canvas,
    camera: s.camera,
    controls: s.controls,
    globe: s.globe,
    minDist: MIN_DIST,
    maxDist: MAX_DIST,
    showMapboxRef: showMapbox,
    rotate,
    getArcballPoint,
    mapbox: () => mapbox,
    touchGestureActive,
    cameraAnimationRef: { current: null },
  })
  /** The layer a new finger lands on: the one the current mode shows. */
  const onMap = () => (showMapbox.current ? mapboxLayer : threeLayer)
  const ev = (type: Kind, id: number, x: number, y: number, pointerType = 'touch', target: Element = onMap()) =>
    ({ type, pointerType, pointerId: id, clientX: x, clientY: y, target }) as unknown as PointerEvent
  const send = (e: PointerEvent) => {
    if (e.type === 'pointerdown') g.onPointerDown(e)
    else if (e.type === 'pointermove') g.onPointerMove(e)
    else g.onPointerEnd(e)
  }
  const dist = () => s.camera.position.length()
  const dir = () => s.camera.position.clone().normalize()
  /** One rendered frame: pending frame callbacks run, then three refreshes the camera matrix. */
  const frame = (ms = 16) => {
    vi.advanceTimersByTime(ms)
    s.camera.updateMatrixWorld()
  }
  return { ...s, g, ev, send, showMapbox, mapbox, touchGestureActive, panel, dist, dir, frame }
}

type H = ReturnType<typeof harness>

/** Two fingers placed `from` px apart around (cx, cy), moved to `to` px apart, one frame per step. */
function pinch(h: H, cx: number, cy: number, from: number, to: number, steps = 6, lift = true) {
  h.send(h.ev('pointerdown', 1, cx - from / 2, cy))
  h.send(h.ev('pointerdown', 2, cx + from / 2, cy))
  for (let i = 1; i <= steps; i++) {
    const gap = from + ((to - from) * i) / steps
    h.send(h.ev('pointermove', 1, cx - gap / 2, cy))
    h.send(h.ev('pointermove', 2, cx + gap / 2, cy))
    h.frame()
  }
  if (lift) {
    h.send(h.ev('pointerup', 1, cx - to / 2, cy))
    h.send(h.ev('pointerup', 2, cx + to / 2, cy))
  }
}

function tap(h: H, x: number, y: number, id = 1) {
  h.send(h.ev('pointerdown', id, x, y))
  h.frame(40)
  h.send(h.ev('pointerup', id, x, y))
}

describe('one finger on the globe', () => {
  it('turns the globe exactly as the same mouse drag does', () => {
    const path: Array<[number, number]> = [[206, 457], [250, 470], [300, 400], [310, 380]]
    const h = harness()
    h.send(h.ev('pointerdown', 1, ...path[0]))
    const after = path.slice(1).map(([x, y]) => {
      h.send(h.ev('pointermove', 1, x, y))
      return round(h.camera.position)
    })
    expect(after).toEqual(mouseDrag(POSE, path).after)
  })

  it('does not zoom, pan or leave the unit sphere around the origin', () => {
    const h = harness()
    const d0 = h.dist()
    h.send(h.ev('pointerdown', 1, 206, 457))
    h.send(h.ev('pointermove', 1, 300, 380))
    expect(h.dist()).toBeCloseTo(d0, 12)
    expect(h.controls.target.length()).toBe(0)
  })
})

describe('what is not a finger on the map', () => {
  it.each(['mouse', 'pen'])('ignores a %s pointer (the mouse handlers own it)', type => {
    const h = harness()
    const before = round(h.camera.position)
    h.send(h.ev('pointerdown', 1, 206, 457, type))
    h.send(h.ev('pointermove', 1, 300, 380, type))
    h.send(h.ev('pointerup', 1, 300, 380, type))
    expect(round(h.camera.position)).toEqual(before)
  })

  it('ignores a finger that lands on a panel', () => {
    const h = harness()
    const before = round(h.camera.position)
    h.send(h.ev('pointerdown', 1, 206, 457, 'touch', h.panel))
    h.send(h.ev('pointermove', 1, 300, 380, 'touch', h.panel))
    expect(round(h.camera.position)).toEqual(before)
    expect(h.touchGestureActive.current).toBe(false)
  })
})

describe('pinch on the globe', () => {
  it('spreading zooms in, pinching together zooms out', () => {
    const inH = harness([10, 30, 2.0])
    pinch(inH, 206, 457.5, 80, 240)
    expect(inH.dist()).toBeLessThan(2.0)

    const outH = harness([10, 30, 1.6])
    pinch(outH, 206, 457.5, 240, 80)
    expect(outH.dist()).toBeGreaterThan(1.6)
  })

  it('zooms by the ratio of the finger distance, not by how often the fingers moved', () => {
    // 80 -> 110 px is a ratio of 1.375: the height above the ground (2.0 - 1)
    // shrinks by it, so the ground under the fingers grows by it.
    const coarse = harness()
    pinch(coarse, 206, 457.5, 80, 110, 2)
    const fine = harness()
    pinch(fine, 206, 457.5, 80, 110, 20)
    expect(coarse.dist()).toBeCloseTo(1 + (1.0 * 80) / 110, 6)
    expect(fine.dist()).toBeCloseTo(1 + (1.0 * 80) / 110, 6)
  })

  it.each([
    ['far out', 2.2, 80, 160],
    ['close to the ground, Mapbox ready', 1.1, 80, 160],
    ['pinching out close to the ground', 1.05, 200, 100],
  ] as const)('keeps the places under both fingers under both fingers (%s)', (_, distance, from, to) => {
    // Apple Maps: what you put your fingers on stays under your fingers. Scaling
    // the distance from the globe centre (the wheel's maths) zoomed close to
    // the ground many times faster than the fingers spread (2026-10-01).
    const h = harness([10, 30, distance], MIN_DIST)
    const cx = 206
    const cy = 457.5
    // The true sphere: near the ground the mesh's facets lie a tenth of the height deep.
    const under = (x: number) => {
      const ray = new THREE.Raycaster()
      ray.setFromCamera(new THREE.Vector2((x / 412) * 2 - 1, -(cy / 915) * 2 + 1), h.camera)
      return ray.ray.intersectSphere(new THREE.Sphere(new THREE.Vector3(), 1), new THREE.Vector3())!
    }
    const left = under(cx - from / 2)
    const right = under(cx + from / 2)

    pinch(h, cx, cy, from, to, 12, false)
    h.camera.updateMatrixWorld()
    const l = screenOf(left, h.camera, h.canvas)
    const r = screenOf(right, h.camera, h.canvas)
    expect(Math.abs(r.x - l.x) / to).toBeCloseTo(1, 1)
    expect(Math.hypot(l.x - (cx - to / 2), l.y - cy)).toBeLessThan(0.05 * to)
    expect(Math.hypot(r.x - (cx + to / 2), r.y - cy)).toBeLessThan(0.05 * to)
  })

  it('keeps the point between the fingers under the fingers', () => {
    // What a pinch does in Apple Maps: the place you pinch stays where you pinch it.
    const h = harness()
    const at = { x: 120, y: 330 }
    const grabbed = h.globe.position.clone() // placeholder
    const hit = new THREE.Raycaster()
    hit.setFromCamera(new THREE.Vector2((at.x / 412) * 2 - 1, -(at.y / 915) * 2 + 1), h.camera)
    grabbed.copy(hit.intersectObject(h.globe, false)[0].point).normalize()

    pinch(h, at.x, at.y, 80, 240)
    h.camera.updateMatrixWorld()
    const now = screenOf(grabbed, h.camera, h.canvas)
    expect(h.dist()).toBeLessThan(1.0 + 0.95) // it did zoom
    expect(Math.hypot(now.x - at.x, now.y - at.y)).toBeLessThan(2)
  })

  it('stops at the closest distance the controls allow, and at the farthest', () => {
    const closeH = harness([10, 30, 1.4])
    pinch(closeH, 206, 457.5, 40, 400)
    expect(closeH.dist()).toBeGreaterThanOrEqual(MAPBOX_SWITCH - 1e-9)

    const farH = harness([10, 30, 2.3])
    pinch(farH, 206, 457.5, 400, 40)
    expect(farH.dist()).toBeLessThanOrEqual(MAX_DIST + 1e-9)
  })

  it('a centred pinch does not turn the globe', () => {
    const h = harness()
    const dir0 = h.dir()
    pinch(h, 206, 457.5, 80, 200)
    expect(h.dir().angleTo(dir0)).toBeLessThan(1e-9)
  })

  it('two fingers dragged together neither zoom, turn nor pan the globe', () => {
    const h = harness()
    const before = round(h.camera.position)
    h.send(h.ev('pointerdown', 1, 166, 457))
    h.send(h.ev('pointerdown', 2, 246, 457))
    // A browser reports the two fingers one pointermove at a time.
    for (let i = 1; i <= 8; i++) {
      h.send(h.ev('pointermove', 1, 166 + i * 10, 457))
      h.send(h.ev('pointermove', 2, 246 + i * 10, 457))
      h.frame()
    }
    expect(round(h.camera.position)).toEqual(before)
    expect(h.controls.target.length()).toBe(0)
  })
})

describe('one gesture across the switch to the Mapbox map and back', () => {
  it('a pinch that crosses into the map goes on zooming the map, at the fingers', () => {
    const h = harness([10, 30, 1.5])
    h.send(h.ev('pointerdown', 1, 166, 457))
    h.send(h.ev('pointerdown', 2, 246, 457))
    h.send(h.ev('pointermove', 1, 156, 457))
    h.send(h.ev('pointermove', 2, 256, 457))
    h.frame()
    const globeAtSwitch = round(h.camera.position)

    h.showMapbox.current = true // the slider reached 66 % mid-gesture
    h.send(h.ev('pointermove', 1, 126, 457))
    h.send(h.ev('pointermove', 2, 286, 457))
    h.frame()

    expect(h.mapbox.zoomAround).toHaveBeenCalledTimes(1)
    const [delta, x, y, animate] = h.mapbox.zoomAround.mock.calls[0]
    expect(delta).toBeCloseTo(Math.log2(160 / 100), 12) // spread 100 -> 160 px
    expect([x, y, animate]).toEqual([206, 457, false])
    expect(round(h.camera.position)).toEqual(globeAtSwitch) // the globe is not zoomed under the map
  })

  it('a pinch that starts on the map is left to Mapbox', () => {
    const h = harness()
    h.showMapbox.current = true
    const before = round(h.camera.position)
    pinch(h, 206, 457, 200, 80)
    expect(h.mapbox.zoomAround).not.toHaveBeenCalled()
    expect(round(h.camera.position)).toEqual(before)
  })

  it('a pinch out that leaves the map goes on zooming out the globe', () => {
    const h = harness([10, 30, 1.2])
    h.showMapbox.current = true
    h.send(h.ev('pointerdown', 1, 106, 457))
    h.send(h.ev('pointerdown', 2, 306, 457))
    h.send(h.ev('pointermove', 1, 126, 457))
    h.send(h.ev('pointermove', 2, 286, 457))
    h.frame()

    h.showMapbox.current = false // the slider fell below 66 % mid-gesture
    h.send(h.ev('pointermove', 1, 166, 457))
    h.send(h.ev('pointermove', 2, 246, 457))
    h.frame()

    // 160 -> 80 px: twice as high above the ground, measured from where the fingers were at the switch
    expect(h.dist()).toBeCloseTo(1 + 0.2 * 2, 6)
    expect(h.mapbox.zoomAround).not.toHaveBeenCalled()
  })

  it('marks the gesture while fingers are down, for the hand-off at the globe scale', () => {
    const h = harness()
    h.send(h.ev('pointerdown', 1, 166, 457))
    expect(h.touchGestureActive.current).toBe(true)
    h.send(h.ev('pointerdown', 2, 246, 457))
    h.send(h.ev('pointerup', 1, 166, 457))
    expect(h.touchGestureActive.current).toBe(true)
    h.send(h.ev('pointerup', 2, 246, 457))
    expect(h.touchGestureActive.current).toBe(false)
  })
})

describe('taps', () => {
  it('a double tap on the map zooms the map in one level at the finger', () => {
    const h = harness()
    h.showMapbox.current = true
    tap(h, 150, 420)
    h.frame(120)
    tap(h, 152, 421)
    expect(h.mapbox.zoomAround).toHaveBeenCalledWith(1, 152, 421, true)
  })

  it('a double tap on the globe is left to the browser dblclick (the desktop double-click zoom)', () => {
    const h = harness()
    const before = round(h.camera.position)
    tap(h, 150, 420)
    h.frame(120)
    tap(h, 152, 421)
    expect(h.mapbox.zoomAround).not.toHaveBeenCalled()
    expect(round(h.camera.position)).toEqual(before)
  })

  it('two taps far apart or slow are no double tap', () => {
    const h = harness()
    h.showMapbox.current = true
    tap(h, 100, 420)
    h.frame(120)
    tap(h, 300, 420)
    h.frame(500)
    tap(h, 300, 420)
    expect(h.mapbox.zoomAround).not.toHaveBeenCalled()
  })

  it('a two-finger tap on the map zooms the map out one level at the fingers', () => {
    const h = harness()
    h.showMapbox.current = true
    h.send(h.ev('pointerdown', 1, 166, 457))
    h.send(h.ev('pointerdown', 2, 246, 457))
    h.frame(60)
    h.send(h.ev('pointerup', 1, 166, 457))
    h.send(h.ev('pointerup', 2, 246, 457))
    expect(h.mapbox.zoomAround).toHaveBeenCalledWith(-1, 206, 457, true)
  })

  it('a two-finger tap on the globe flies three steps out, keeping the view centre', () => {
    const h = harness([10, 30, 1.6])
    const dir0 = h.dir()
    h.send(h.ev('pointerdown', 1, 166, 457))
    h.send(h.ev('pointerdown', 2, 246, 457))
    h.frame(60)
    h.send(h.ev('pointerup', 1, 166, 457))
    h.send(h.ev('pointerup', 2, 246, 457))
    vi.advanceTimersByTime(600)
    expect(h.dist()).toBeCloseTo(Math.min(MAX_DIST, 1.6 + (3 * (MAX_DIST - MIN_DIST)) / 10), 9)
    expect(h.dir().angleTo(dir0)).toBeLessThan(1e-9)
  })

  it('a pinch is no two-finger tap', () => {
    const h = harness()
    h.showMapbox.current = true
    pinch(h, 206, 457, 200, 80)
    expect(h.mapbox.zoomAround).not.toHaveBeenCalled()
  })
})

describe('inertia after a flick on the globe', () => {
  /** A finger that sweeps 10px per 16ms and lifts right away. */
  function flick(h: H, liftAfterMs = 0) {
    h.send(h.ev('pointerdown', 1, 150, 457))
    for (let i = 1; i <= 6; i++) {
      vi.advanceTimersByTime(16)
      h.send(h.ev('pointermove', 1, 150 + i * 10, 457))
    }
    vi.advanceTimersByTime(liftAfterMs)
    h.send(h.ev('pointerup', 1, 210, 457))
  }

  it('keeps the globe turning after the finger lifts, then comes to rest by itself', () => {
    const h = harness()
    flick(h)
    const atLift = round(h.camera.position)
    vi.advanceTimersByTime(48)
    expect(round(h.camera.position)).not.toEqual(atLift)
    vi.advanceTimersByTime(5000)
    const settled = round(h.camera.position)
    vi.advanceTimersByTime(1000)
    expect(round(h.camera.position)).toEqual(settled)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('turns the same way the finger was moving', () => {
    const h = harness()
    const lng = () => (Math.atan2(h.camera.position.z, -h.camera.position.x) * 180) / Math.PI
    const turn = (a: number, b: number) => ((((b - a) % 360) + 540) % 360) - 180
    const before = lng()
    flick(h)
    const atLift = lng()
    vi.advanceTimersByTime(2000)
    const after = lng()
    expect(turn(before, atLift)).not.toBe(0)
    expect(Math.sign(turn(atLift, after))).toBe(Math.sign(turn(before, atLift)))
    expect(Math.abs(turn(atLift, after))).toBeGreaterThan(1)
  })

  it('has no inertia when the finger rested before lifting, or after a slow drag', () => {
    const rested = harness()
    flick(rested, 250)
    const restedAt = round(rested.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(rested.camera.position)).toEqual(restedAt)

    const slow = harness()
    slow.send(slow.ev('pointerdown', 1, 150, 457))
    for (let i = 1; i <= 6; i++) {
      vi.advanceTimersByTime(100)
      slow.send(slow.ev('pointermove', 1, 150 + i, 457))
    }
    slow.send(slow.ev('pointerup', 1, 156, 457))
    const slowAt = round(slow.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(slow.camera.position)).toEqual(slowAt)
  })

  it('has no inertia after pointercancel or after a pinch', () => {
    const cancelled = harness()
    cancelled.send(cancelled.ev('pointerdown', 1, 150, 457))
    for (let i = 1; i <= 6; i++) {
      vi.advanceTimersByTime(16)
      cancelled.send(cancelled.ev('pointermove', 1, 150 + i * 10, 457))
    }
    cancelled.send(cancelled.ev('pointercancel', 1, 210, 457))
    const at = round(cancelled.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(cancelled.camera.position)).toEqual(at)

    const pinched = harness()
    pinch(pinched, 206, 457.5, 110, 230)
    const atLift = round(pinched.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(pinched.camera.position)).toEqual(atLift)
  })

  it('stops when a finger touches down, when Mapbox takes over, and on dispose', () => {
    const touched = harness()
    flick(touched)
    vi.advanceTimersByTime(32)
    touched.send(touched.ev('pointerdown', 2, 100, 600))
    const held = round(touched.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(touched.camera.position)).toEqual(held)

    const mapped = harness()
    flick(mapped)
    vi.advanceTimersByTime(32)
    mapped.showMapbox.current = true
    const heldMap = round(mapped.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(mapped.camera.position)).toEqual(heldMap)

    const disposed = harness()
    flick(disposed)
    vi.advanceTimersByTime(32)
    disposed.g.dispose()
    const heldDisposed = round(disposed.camera.position)
    vi.advanceTimersByTime(2000)
    expect(round(disposed.camera.position)).toEqual(heldDisposed)
    expect(vi.getTimerCount()).toBe(0)
  })
})
