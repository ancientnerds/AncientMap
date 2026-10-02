/**
 * @vitest-environment jsdom
 *
 * setupEventHandlers: what it attaches, and where.
 *
 * Touch input was added next to the mouse and wheel handlers on 2026-10-01 and
 * moved the same day from the Three.js canvas to the element both map layers
 * sit in, so one gesture lives on across a switch between globe and map. These
 * tests pin that the touch listeners sit there (capture phase) and are removed,
 * that OrbitControls no longer takes touch (its pan dragged the globe out of
 * the middle), and that every listener the desktop relied on is still there.
 */
import { describe, it, expect, vi } from 'vitest'
import * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { setupEventHandlers, type EventHandlerRefs } from '../eventHandlers'
import { MIN_DIST, MAX_DIST, MAPBOX_SWITCH, scene, position, round } from './cameraFixtures'

function wired(showMapbox = false) {
  const s = scene([10, 30, 2.0])
  // Globe.tsx: .globe-wrapper > .mapbox-globe-container + .globe-container > canvas, plus panels
  const wrapper = document.createElement('div')
  const mapboxContainer = document.createElement('div')
  const threeContainer = document.createElement('div')
  const canvasEl = document.createElement('canvas')
  const panel = document.createElement('div')
  canvasEl.getBoundingClientRect = s.canvas.getBoundingClientRect
  threeContainer.appendChild(canvasEl)
  wrapper.append(mapboxContainer, threeContainer, panel)
  document.body.appendChild(wrapper)

  const canvasAdd = vi.spyOn(canvasEl, 'addEventListener')
  const canvasRemove = vi.spyOn(canvasEl, 'removeEventListener')
  const wrapperAdd = vi.spyOn(wrapper, 'addEventListener')
  const wrapperRemove = vi.spyOn(wrapper, 'removeEventListener')
  const windowAdd = vi.spyOn(window, 'addEventListener')

  const controls = {
    minDistance: MAPBOX_SWITCH,
    target: new THREE.Vector3(),
    update: vi.fn(),
    addEventListener: vi.fn(),
    touches: { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN },
    enableZoom: true,
  } as unknown as OrbitControls

  const mapbox = { zoomAround: vi.fn() }
  const touchGestureActive = { current: false }
  const refs = {
    containerRef: { current: threeContainer },
    mapboxContainerRef: { current: mapboxContainer },
    touchGestureActive,
    mapboxServiceRef: { current: mapbox },
    cameraAnimationRef: { current: null },
    showMapboxRef: { current: showMapbox },
    zoomRef: { current: 0 },
  } as unknown as EventHandlerRefs
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
  const done = () => {
    cleanup()
    wrapper.remove()
  }
  return { s, canvasEl, mapboxContainer, panel, controls, mapbox, touchGestureActive, done, canvasAdd, canvasRemove, wrapperAdd, wrapperRemove, windowAdd, names }
}

function pointer(type: string, id: number, x: number, y: number, pointerType = 'touch') {
  return new (class extends Event {
    pointerType = pointerType
    pointerId = id
    clientX = x
    clientY = y
  })(type, { bubbles: true })
}

describe('setupEventHandlers', () => {
  it('takes touch away from OrbitControls and leaves its mouse buttons alone', () => {
    const w = wired()
    expect(w.controls.touches).toEqual({ ONE: null, TWO: null })
    expect(w.controls.enableZoom).toBe(false)
    w.done()
  })

  it('keeps every listener the desktop uses on the canvas', () => {
    const w = wired()
    expect([...new Set(w.names(w.canvasAdd))].sort()).toEqual(
      ['click', 'dblclick', 'mousedown', 'mouseleave', 'mousemove', 'wheel'].sort(),
    )
    expect(w.names(w.windowAdd)).toEqual(expect.arrayContaining(['resize', 'wheel', 'mouseup']))
    w.done()
  })

  it('reads touch on the element both map layers sit in, in the capture phase', () => {
    const w = wired()
    const touchCalls = w.wrapperAdd.mock.calls.filter(c => String(c[0]).startsWith('pointer'))
    expect(touchCalls.map(c => c[0]).sort()).toEqual(['pointercancel', 'pointerdown', 'pointermove', 'pointerup'])
    for (const call of touchCalls) expect(call[2]).toEqual({ capture: true })
    w.done()
  })

  it('removes exactly what it attached', () => {
    const w = wired()
    w.done()
    expect(w.names(w.canvasRemove).sort()).toEqual(w.names(w.canvasAdd).sort())
    expect(w.names(w.wrapperRemove).sort()).toEqual(w.names(w.wrapperAdd).sort())
  })

  it('turns the globe under a finger on the globe, and not under a mouse pointer', () => {
    const w = wired()
    const before = round(w.s.camera.position)

    w.canvasEl.dispatchEvent(pointer('pointerdown', 1, 206, 457, 'mouse'))
    w.canvasEl.dispatchEvent(pointer('pointermove', 1, 300, 380, 'mouse'))
    expect(round(w.s.camera.position)).toEqual(before)

    w.canvasEl.dispatchEvent(pointer('pointerdown', 2, 206, 457))
    w.canvasEl.dispatchEvent(pointer('pointermove', 2, 300, 380))
    expect(round(w.s.camera.position)).not.toEqual(before)
    expect(w.s.camera.position.length()).toBeCloseTo(position(10, 30, 2.0).length(), 10)
    expect(w.controls.target.length()).toBe(0)
    w.done()
  })

  it('ignores a finger on a panel', () => {
    const w = wired()
    const before = round(w.s.camera.position)
    w.panel.dispatchEvent(pointer('pointerdown', 1, 206, 457))
    w.panel.dispatchEvent(pointer('pointermove', 1, 300, 380))
    expect(round(w.s.camera.position)).toEqual(before)
    expect(w.touchGestureActive.current).toBe(false)
    w.done()
  })

  it('sees a gesture on the Mapbox layer too (a double tap there zooms the map)', () => {
    vi.useFakeTimers({ toFake: ['performance'] })
    const w = wired(true)
    for (const t of [0, 1]) {
      w.mapboxContainer.dispatchEvent(pointer('pointerdown', 1, 150, 420))
      vi.advanceTimersByTime(40)
      w.mapboxContainer.dispatchEvent(pointer('pointerup', 1, 150, 420))
      if (t === 0) vi.advanceTimersByTime(100)
    }
    vi.useRealTimers()
    expect(w.mapbox.zoomAround).toHaveBeenCalledWith(1, 150, 420, true)
    w.done()
  })

  it('does not react to a finger once cleaned up', () => {
    const w = wired()
    w.done()
    const before = round(w.s.camera.position)
    w.canvasEl.dispatchEvent(pointer('pointerdown', 1, 206, 457))
    w.canvasEl.dispatchEvent(pointer('pointermove', 1, 300, 380))
    expect(round(w.s.camera.position)).toEqual(before)
  })
})
