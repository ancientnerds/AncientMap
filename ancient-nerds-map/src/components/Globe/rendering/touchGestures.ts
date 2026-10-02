import type * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLOBE } from '../../../config/globeConstants'
import {
  animateCameraTo,
  canvasNDC,
  screenOf,
  zoomCameraBy,
  type ScreenPoint,
} from './cameraMotion'

/**
 * Finger control of the globe and the map, the way Apple Maps does it: one
 * finger turns the globe, two fingers pinch (the place between them stays
 * under them), a double tap zooms in, a two-finger tap zooms out.
 *
 * 2026-10-01: the globe had no touch handling of its own (mouse and wheel only;
 * OrbitControls' pan dragged it out of the middle). The first version (morning)
 * pinched toward the fingers instead of keeping their place, and at 66 % its
 * gesture died: the slider switched to the Mapbox map, the fingers were still
 * on the Three.js canvas, and a pinch on the map never moved the slider back -
 * the owner could zoom in but not out again.
 *
 * So touch is read on the element both map layers sit in (setupEventHandlers
 * listens there, in the capture phase): a gesture keeps its fingers across a
 * switch between the globe and the map, both ways. Who acts:
 *
 *   gesture started on    globe shown              map shown
 *   the globe             here (globe)             here (map, via zoomAround)
 *   the map               here (globe)             Mapbox's own pinch and pan
 *
 * A map zoom made here or by Mapbox's own pinch reaches the slider through
 * MapboxGlobeService.onTouchZoom; pinching out below the map's entry zoom
 * brings the globe back. Only `pointerType === 'touch'` is handled; mouse and
 * pen stay with the mouse handlers.
 */

/** A tap: the fingers are down no longer than this. */
const TAP_MAX_MS = 250
/** Movement up to this many pixels still counts as a tap. */
const TAP_SLOP_PX = 10
/** Two taps within this time and distance are a double tap. */
const DOUBLE_TAP_MS = 300
const DOUBLE_TAP_PX = 40

/** A finger that rests this long before lifting is a placement, not a flick. */
const FLICK_MAX_REST_MS = 80
/** Release speed (px per ms) from which the globe keeps gliding. */
const GLIDE_MIN_SPEED = 0.1
/** Glide speed (px per ms) below which it has come to rest. */
const GLIDE_STOP_SPEED = 0.02
const GLIDE_FRAME_MS = 1000 / 60
/** Speed kept per 60 Hz frame. */
const GLIDE_DECAY_PER_FRAME = 0.95
/** A long frame (tab in the background, GC) must not become one huge step. */
const GLIDE_MAX_FRAME_MS = 32

/** What the gestures need from the Mapbox map (MapboxGlobeService). */
export interface TouchMap {
  zoomAround: (deltaZoom: number, clientX: number, clientY: number, animate: boolean) => void
}

export interface TouchGestureDeps {
  /** The Three.js and the Mapbox layer: a gesture counts only when it starts on one of them, not on a panel. */
  mapLayers: Element[]
  canvas: HTMLCanvasElement
  camera: THREE.PerspectiveCamera
  controls: OrbitControls
  globe: THREE.Mesh
  minDist: number
  maxDist: number
  /** True while the Mapbox map is shown. */
  showMapboxRef: React.MutableRefObject<boolean>
  /** The arcball drag, the same function the mouse handler calls. */
  rotate: (from: ScreenPoint, to: ScreenPoint) => void
  getArcballPoint: (clientX: number, clientY: number) => THREE.Vector3 | null
  mapbox: () => TouchMap | null
  /** Raised while fingers are down: a switch to the map now is a pinch and keeps the globe's scale. */
  touchGestureActive: React.MutableRefObject<boolean>
  cameraAnimationRef: React.MutableRefObject<number | null>
}

export interface TouchGestures {
  onPointerDown: (e: PointerEvent) => void
  onPointerMove: (e: PointerEvent) => void
  /** pointerup and pointercancel. */
  onPointerEnd: (e: PointerEvent) => void
  /** Stops a glide in progress. */
  dispose: () => void
}

interface Finger {
  start: ScreenPoint
  at: ScreenPoint
}

export function createTouchGestures(deps: TouchGestureDeps): TouchGestures {
  const { mapLayers, canvas, camera, controls, globe, minDist, maxDist, showMapboxRef, rotate, getArcballPoint, mapbox } = deps

  const fingers = new Map<number, Finger>()
  /** Which layer the gesture started on; it decides who acts while the map is shown. */
  let startedOnMap = false
  /** Most fingers down at once in this gesture, when it began, and whether they travelled. */
  let maxFingers = 0
  let gestureStart = 0
  let moved = false
  let pinchSpan = 0
  let pinchFrame: number | null = null
  /**
   * The globe point the pinch grabbed and where on screen it was grabbed. Held
   * for the whole pinch on the globe: each frame brings this point back to this
   * place, so the arcball's small roll error corrects itself instead of adding
   * up frame by frame (re-grabbing every frame let the place drift 12 px).
   */
  let pinchAnchor: { point: THREE.Vector3 | null; screen: ScreenPoint } | null = null
  /** Smoothed one-finger speed in px per ms; the glide's start speed. */
  let velocity = { x: 0, y: 0 }
  let lastMoveAt = 0
  let glideFrame: number | null = null
  let lastTap: { at: ScreenPoint; time: number } | null = null
  /** Where the two fingers of a possible two-finger tap were, while the second one lifts. */
  let pendingTwoFingerTap: ScreenPoint | null = null

  const onMapNow = () => showMapboxRef.current
  /** In map mode only a gesture that started on the globe is ours; Mapbox drives its own. */
  const actsHere = () => !onMapNow() || !startedOnMap

  const positions = () => [...fingers.values()].map(f => f.at)
  const span = (): number => {
    const [a, b] = positions()
    return Math.hypot(a.x - b.x, a.y - b.y)
  }
  const midpoint = (): ScreenPoint => {
    const [a, b] = positions()
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
  }

  /**
   * Zoom the globe by `scale` keeping the pinch's grabbed point where it was
   * grabbed: first the distance, then the arcball turn that carries the point
   * back to its place on screen.
   *
   * `scale` applies to the height above the ground, not to the distance from
   * the globe centre: the ground grows on screen as the height shrinks, so it
   * grows with the finger span and stays under the fingers. The wheel's
   * distance factor zoomed near the ground many times faster than the fingers
   * moved (from 1.05 a small squeeze threw the view out to 2.1).
   */
  const zoomGlobe = (scale: number, at: ScreenPoint) => {
    camera.updateMatrixWorld()
    if (!pinchAnchor) pinchAnchor = { point: getArcballPoint(at.x, at.y), screen: at }
    const { point, screen } = pinchAnchor
    const distance = camera.position.length()
    const target = GLOBE.RADIUS + (distance - GLOBE.RADIUS) * scale
    zoomCameraBy(camera, controls, globe, minDist, maxDist, target / distance, canvasNDC(screen.x, screen.y, canvas), 0)
    if (!point) return
    camera.updateMatrixWorld()
    rotate(screenOf(point, camera, canvas), screen)
  }

  /**
   * One zoom step from where both fingers are NOW, once per frame. Browsers
   * report the two fingers one pointermove at a time; between the two reports
   * the distance is momentarily wrong, and a per-event zoom made a sideways
   * two-finger drag zoom out and in. The span is kept current even when
   * Mapbox drives, so the globe takes over smoothly if the gesture leaves the map.
   */
  const applyPinch = () => {
    pinchFrame = null
    if (fingers.size !== 2) return
    const now = span()
    // The anchor belongs to the globe: on the map Mapbox anchors itself, and a
    // pinch that comes back to the globe grabs afresh.
    if (onMapNow()) pinchAnchor = null
    if (pinchSpan > 0 && now > 0 && actsHere()) {
      const mid = midpoint()
      if (onMapNow()) {
        mapbox()?.zoomAround(Math.log2(now / pinchSpan), mid.x, mid.y, false)
      } else {
        zoomGlobe(pinchSpan / now, mid)
      }
    }
    pinchSpan = now
  }

  const flushPinch = () => {
    if (pinchFrame === null) return
    cancelAnimationFrame(pinchFrame)
    applyPinch()
  }

  const stopGlide = () => {
    if (glideFrame !== null) {
      cancelAnimationFrame(glideFrame)
      glideFrame = null
    }
  }

  const startGlide = (from: ScreenPoint) => {
    let point = { ...from }
    let last = performance.now()
    const step = (now: number) => {
      // The map took over mid-glide: it is Mapbox's now.
      if (onMapNow()) {
        glideFrame = null
        return
      }
      // rAF's timestamp is the frame start, which can precede performance.now()
      // at the call that scheduled it: never step backwards.
      const dt = Math.min(GLIDE_MAX_FRAME_MS, Math.max(0, now - last))
      last = now
      const to = { x: point.x + velocity.x * dt, y: point.y + velocity.y * dt }
      rotate(point, to)
      point = to
      const keep = Math.pow(GLIDE_DECAY_PER_FRAME, dt / GLIDE_FRAME_MS)
      velocity = { x: velocity.x * keep, y: velocity.y * keep }
      if (Math.hypot(velocity.x, velocity.y) < GLIDE_STOP_SPEED) {
        glideFrame = null
        return
      }
      glideFrame = requestAnimationFrame(step)
    }
    glideFrame = requestAnimationFrame(step)
  }

  /** Two-finger tap on the globe: three steps out, the mirror of the double click's three steps in. */
  const zoomGlobeOut = () => {
    const distance = Math.min(maxDist, camera.position.length() + (3 * (maxDist - minDist)) / 10)
    animateCameraTo(camera, controls, camera.position.clone().normalize().multiplyScalar(distance), deps.cameraAnimationRef)
  }

  const onPointerDown = (e: PointerEvent) => {
    if (e.pointerType !== 'touch') return
    if (fingers.size === 0) {
      if (!mapLayers.some(layer => layer.contains(e.target as Node))) return
      startedOnMap = onMapNow()
      maxFingers = 0
      moved = false
      gestureStart = performance.now()
      deps.touchGestureActive.current = true
    }
    stopGlide()
    const at = { x: e.clientX, y: e.clientY }
    fingers.set(e.pointerId, { start: at, at })
    maxFingers = Math.max(maxFingers, fingers.size)
    velocity = { x: 0, y: 0 }
    lastMoveAt = performance.now()
    if (fingers.size === 2) {
      pinchSpan = span()
      pinchAnchor = null
      gestureStart = performance.now()
    }
  }

  const onPointerMove = (e: PointerEvent) => {
    if (e.pointerType !== 'touch') return
    const finger = fingers.get(e.pointerId)
    if (!finger) return
    const from = finger.at
    const to = { x: e.clientX, y: e.clientY }
    finger.at = to
    if (Math.hypot(to.x - finger.start.x, to.y - finger.start.y) > TAP_SLOP_PX) moved = true

    if (fingers.size === 1 && !onMapNow()) {
      rotate(from, to)
      const now = performance.now()
      const dt = Math.max(1, now - lastMoveAt)
      lastMoveAt = now
      velocity = {
        x: 0.5 * velocity.x + (0.5 * (to.x - from.x)) / dt,
        y: 0.5 * velocity.y + (0.5 * (to.y - from.y)) / dt,
      }
    } else if (fingers.size === 2 && pinchFrame === null) {
      pinchFrame = requestAnimationFrame(applyPinch)
    }
    // A third finger is tracked so that lifting it is clean, but moves nothing.
  }

  /** A tap or a two-finger tap that just ended: zoom, if it is one. */
  const handleTap = (at: ScreenPoint, twoFingers: ScreenPoint | null) => {
    const now = performance.now()
    if (moved || now - gestureStart > TAP_MAX_MS) {
      lastTap = null
      return
    }
    if (twoFingers) {
      lastTap = null
      if (onMapNow()) mapbox()?.zoomAround(-1, twoFingers.x, twoFingers.y, true)
      else zoomGlobeOut()
      return
    }
    // A double tap on the globe is the browser's dblclick, which the desktop
    // double-click zoom already handles; on the map Mapbox's own is off.
    if (lastTap && now - lastTap.time <= DOUBLE_TAP_MS && Math.hypot(at.x - lastTap.at.x, at.y - lastTap.at.y) <= DOUBLE_TAP_PX) {
      lastTap = null
      if (onMapNow()) mapbox()?.zoomAround(1, at.x, at.y, true)
      return
    }
    lastTap = { at, time: now }
  }

  const onPointerEnd = (e: PointerEvent) => {
    if (e.pointerType !== 'touch') return
    const finger = fingers.get(e.pointerId)
    if (!finger) return
    flushPinch()
    const wasLone = fingers.size === 1
    const twoFingerMid = fingers.size === 2 && maxFingers === 2 ? midpoint() : null
    fingers.delete(e.pointerId)

    // A different pair of fingers, or none: the next pinch grabs afresh.
    pinchAnchor = null
    if (fingers.size === 2) pinchSpan = span()
    if (fingers.size === 1) {
      // A pinch turned back into a one-finger drag: no speed to inherit.
      velocity = { x: 0, y: 0 }
      lastMoveAt = performance.now()
      if (twoFingerMid && e.type === 'pointerup') pendingTwoFingerTap = twoFingerMid
      return
    }
    if (fingers.size > 0) return

    // The last finger lifted: the gesture is over.
    deps.touchGestureActive.current = false
    if (e.type !== 'pointerup') {
      pendingTwoFingerTap = null
      return
    }
    if (maxFingers === 2 && pendingTwoFingerTap) {
      handleTap(finger.at, pendingTwoFingerTap)
    } else if (maxFingers === 1) {
      handleTap(finger.at, null)
    }
    pendingTwoFingerTap = null
    if (
      wasLone &&
      maxFingers === 1 &&
      !onMapNow() &&
      performance.now() - lastMoveAt <= FLICK_MAX_REST_MS &&
      Math.hypot(velocity.x, velocity.y) >= GLIDE_MIN_SPEED
    ) {
      startGlide(finger.at)
    }
  }

  const dispose = () => {
    stopGlide()
    if (pinchFrame !== null) {
      cancelAnimationFrame(pinchFrame)
      pinchFrame = null
    }
    fingers.clear()
    deps.touchGestureActive.current = false
  }

  return { onPointerDown, onPointerMove, onPointerEnd, dispose }
}
