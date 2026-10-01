import type * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { WHEEL_ZOOM_STEP, canvasNDC, zoomCameraBy, type ScreenPoint } from './cameraMotion'

/**
 * Finger control of the globe: one finger turns it, two fingers pinch-zoom it.
 *
 * Until 2026-10-01 the globe had no touch handling of its own: rotation and
 * zoom were mouse and wheel only, OrbitControls' own touch rotate/zoom were
 * switched off, and its pan was not — so one finger did nothing and two
 * fingers dragged the globe out of the middle. Setting `controls.touches` to
 * none (setupEventHandlers) leaves OrbitControls out of touch entirely; this
 * is the touch input, built on the mouse's maths (cameraMotion.ts) so a finger
 * drag is the mouse drag, not an imitation of it.
 *
 * Only `pointerType === 'touch'` is handled: mouse and pen stay with the mouse
 * handlers, and a hybrid laptop uses each input as it is.
 */

/** A pinch frame leans toward the fingers at most as far as this many wheel notches. */
const PINCH_MAX_LEAN_STEPS = 3

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

export interface TouchGestureDeps {
  canvas: HTMLCanvasElement
  camera: THREE.PerspectiveCamera
  controls: OrbitControls
  globe: THREE.Mesh
  minDist: number
  maxDist: number
  /** True while Mapbox shows the map: its own gestures take over, as for the mouse. */
  showMapboxRef: React.MutableRefObject<boolean>
  /** The arcball drag, the same function the mouse handler calls. */
  rotate: (from: ScreenPoint, to: ScreenPoint) => void
}

export interface TouchGestures {
  onPointerDown: (e: PointerEvent) => void
  onPointerMove: (e: PointerEvent) => void
  /** pointerup and pointercancel. */
  onPointerEnd: (e: PointerEvent) => void
  /** Stops a glide in progress. */
  dispose: () => void
}

export function createTouchGestures(deps: TouchGestureDeps): TouchGestures {
  const { canvas, camera, controls, globe, minDist, maxDist, showMapboxRef, rotate } = deps

  const fingers = new Map<number, ScreenPoint>()
  let pinchSpan = 0
  /** Smoothed finger speed in px per ms; the glide's start speed. */
  let velocity = { x: 0, y: 0 }
  let lastMoveAt = 0
  let glideFrame: number | null = null
  let pinchFrame: number | null = null

  const span = (): number => {
    const [a, b] = [...fingers.values()]
    return Math.hypot(a.x - b.x, a.y - b.y)
  }

  /**
   * One zoom step from where both fingers are NOW.
   *
   * Browsers report the two fingers of a pinch one pointermove at a time. Between
   * the two reports the finger distance is momentarily wrong: dragging both
   * fingers together sideways would zoom out and back in on every step, and the
   * zoom-in half leans toward the fingers each time, so the globe would drift.
   * Applying the pinch once per frame uses both fingers' positions of that
   * frame. (The one-finger drag needs no such care: one finger, one position.)
   */
  const applyPinch = () => {
    pinchFrame = null
    if (fingers.size !== 2) return
    const now = span()
    if (!showMapboxRef.current && pinchSpan > 0 && now > 0) {
      const [a, b] = [...fingers.values()]
      const between = canvasNDC((a.x + b.x) / 2, (a.y + b.y) / 2, canvas)
      // Fingers moving apart shorten the camera distance by the same ratio.
      const scale = pinchSpan / now
      const lean = Math.min(PINCH_MAX_LEAN_STEPS, Math.abs(scale - 1) / WHEEL_ZOOM_STEP)
      zoomCameraBy(camera, controls, globe, minDist, maxDist, scale, between, lean)
    }
    pinchSpan = now
  }

  /** Settle a pinch frame still waiting, before the fingers change. */
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
      // Mapbox took over mid-glide: the map is theirs now.
      if (showMapboxRef.current) {
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

  const onPointerDown = (e: PointerEvent) => {
    if (e.pointerType !== 'touch' || showMapboxRef.current) return
    stopGlide()
    fingers.set(e.pointerId, { x: e.clientX, y: e.clientY })
    velocity = { x: 0, y: 0 }
    lastMoveAt = performance.now()
    if (fingers.size === 2) pinchSpan = span()
  }

  const onPointerMove = (e: PointerEvent) => {
    if (e.pointerType !== 'touch' || showMapboxRef.current) return
    const from = fingers.get(e.pointerId)
    if (!from) return
    const to = { x: e.clientX, y: e.clientY }
    fingers.set(e.pointerId, to)

    if (fingers.size === 1) {
      rotate(from, to)
      const now = performance.now()
      const dt = Math.max(1, now - lastMoveAt)
      lastMoveAt = now
      velocity = {
        x: 0.5 * velocity.x + (0.5 * (to.x - from.x)) / dt,
        y: 0.5 * velocity.y + (0.5 * (to.y - from.y)) / dt,
      }
    } else if (fingers.size === 2) {
      if (pinchFrame === null) pinchFrame = requestAnimationFrame(applyPinch)
    }
    // A third finger is tracked so that lifting it is clean, but moves nothing.
  }

  const onPointerEnd = (e: PointerEvent) => {
    if (e.pointerType !== 'touch') return
    const last = fingers.get(e.pointerId)
    if (!last) return
    flushPinch()
    const wasLone = fingers.size === 1
    fingers.delete(e.pointerId)

    if (fingers.size === 2) pinchSpan = span()
    if (fingers.size === 1) {
      // A pinch turned back into a one-finger drag: no speed to inherit.
      velocity = { x: 0, y: 0 }
      lastMoveAt = performance.now()
    }
    if (
      wasLone &&
      e.type === 'pointerup' &&
      performance.now() - lastMoveAt <= FLICK_MAX_REST_MS &&
      Math.hypot(velocity.x, velocity.y) >= GLIDE_MIN_SPEED
    ) {
      startGlide(last)
    }
  }

  const dispose = () => {
    stopGlide()
    if (pinchFrame !== null) {
      cancelAnimationFrame(pinchFrame)
      pinchFrame = null
    }
    fingers.clear()
  }

  return { onPointerDown, onPointerMove, onPointerEnd, dispose }
}
