/**
 * @vitest-environment jsdom
 *
 * setupEventHandlers: what it attaches to the canvas.
 *
 * Touch input was added next to the mouse and wheel handlers on 2026-10-01.
 * These tests pin that the touch listeners are attached and removed, that
 * OrbitControls no longer takes touch (its pan dragged the globe out of the
 * middle), and that every listener the desktop relied on is still there.
 */
import { describe, it, expect, vi } from 'vitest'
import * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { setupEventHandlers, type EventHandlerRefs } from '../eventHandlers'
import { MIN_DIST, MAX_DIST, MAPBOX_SWITCH, scene, position, round } from './cameraFixtures'

function wired(showMapbox = false) {
  const s = scene([10, 30, 2.0])
  const canvasEl = document.createElement('canvas')
  canvasEl.getBoundingClientRect = s.canvas.getBoundingClientRect
  const canvasAdd = vi.spyOn(canvasEl, 'addEventListener')
  const canvasRemove = vi.spyOn(canvasEl, 'removeEventListener')
  const windowAdd = vi.spyOn(window, 'addEventListener')

  const controls = {
    minDistance: MAPBOX_SWITCH,
    target: new THREE.Vector3(),
    update: vi.fn(),
    addEventListener: vi.fn(),
    touches: { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN },
    enableZoom: true,
  } as unknown as OrbitControls

  const refs = { showMapboxRef: { current: showMapbox }, zoomRef: { current: 0 } } as unknown as EventHandlerRefs
  const { cleanup } = setupEventHandlers(
    {
      renderer: { domElement: canvasEl } as unknown as THREE.WebGLRenderer,
      camera: s.camera,
      controls,
      globe: s.globe,
      minDist: MIN_DIST,
      maxDist: MAX_DIST,
    },
    refs,
    { setZoom: vi.fn(), setCursorCoords: vi.fn(), setTooltipPos: vi.fn(), setHoveredSite: vi.fn(), setIsFrozen: vi.fn(), setFrozenSite: vi.fn() },
    {},
    { current: false },
  )
  const names = (spy: typeof canvasAdd) => spy.mock.calls.map(c => c[0])
  return { s, canvasEl, controls, cleanup, canvasAdd, canvasRemove, windowAdd, names }
}

function touchEvent(type: string, id: number, x: number, y: number, pointerType = 'touch') {
  return Object.assign(new Event(type), { pointerType, pointerId: id, clientX: x, clientY: y })
}

describe('setupEventHandlers', () => {
  it('takes touch away from OrbitControls and leaves its mouse buttons alone', () => {
    const w = wired()
    expect(w.controls.touches).toEqual({ ONE: null, TWO: null })
    // untouched by this change: the wheel zoom is ours
    expect(w.controls.enableZoom).toBe(false)
    w.cleanup()
  })

  it('attaches the touch listeners next to every listener the desktop uses', () => {
    const w = wired()
    expect([...new Set(w.names(w.canvasAdd))].sort()).toEqual(
      ['click', 'dblclick', 'mousedown', 'mouseleave', 'mousemove', 'pointercancel', 'pointerdown', 'pointermove', 'pointerup', 'wheel'].sort(),
    )
    expect(w.names(w.windowAdd)).toEqual(expect.arrayContaining(['resize', 'wheel', 'mouseup']))
    w.cleanup()
  })

  it('removes exactly what it attached from the canvas', () => {
    const w = wired()
    w.cleanup()
    expect(w.names(w.canvasRemove).sort()).toEqual(w.names(w.canvasAdd).sort())
  })

  it('turns the globe under a finger on the canvas, and not under a mouse pointer', () => {
    const w = wired()
    const before = round(w.s.camera.position)

    w.canvasEl.dispatchEvent(touchEvent('pointerdown', 1, 206, 457, 'mouse'))
    w.canvasEl.dispatchEvent(touchEvent('pointermove', 1, 300, 380, 'mouse'))
    expect(round(w.s.camera.position)).toEqual(before)

    w.canvasEl.dispatchEvent(touchEvent('pointerdown', 2, 206, 457))
    w.canvasEl.dispatchEvent(touchEvent('pointermove', 2, 300, 380))
    expect(round(w.s.camera.position)).not.toEqual(before)
    // and stays on the sphere around the origin, pan-free
    expect(w.s.camera.position.length()).toBeCloseTo(position(10, 30, 2.0).length(), 10)
    expect(w.controls.target.length()).toBe(0)
    w.cleanup()
  })

  it('does not react to a finger once cleaned up', () => {
    const w = wired()
    w.cleanup()
    const before = round(w.s.camera.position)
    w.canvasEl.dispatchEvent(touchEvent('pointerdown', 1, 206, 457))
    w.canvasEl.dispatchEvent(touchEvent('pointermove', 1, 300, 380))
    expect(round(w.s.camera.position)).toEqual(before)
  })

  it('leaves a finger to Mapbox while it shows the map', () => {
    const w = wired(true)
    const before = round(w.s.camera.position)
    w.canvasEl.dispatchEvent(touchEvent('pointerdown', 1, 206, 457))
    w.canvasEl.dispatchEvent(touchEvent('pointermove', 1, 300, 380))
    expect(round(w.s.camera.position)).toEqual(before)
    w.cleanup()
  })
})
